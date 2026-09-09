import asyncio
import gc
import math
import subprocess
import sys
import wave
from pathlib import Path

# Production V2:
# story -> AI character/scene anchors -> Wan I2V -> Hindi narration -> original kids music -> QC-ready MP4.
# Wan is deliberately the expensive final stage; no Wan call is made during anchor preparation.

subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "diffusers>=0.36.0", "transformers>=4.49.0", "accelerate>=1.5.0",
    "safetensors", "imageio[ffmpeg]", "edge-tts", "pillow",
    "google-genai", "google-api-python-client", "google-auth",
])

import torch
from PIL import Image
from diffusers import AutoPipelineForText2Image, AutoPipelineForImage2Image, WanImageToVideoPipeline
from diffusers.utils import export_to_video

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from toon_kids_story import local_story, load_history  # noqa: E402

OUT = Path("/kaggle/working")
WIDTH, HEIGHT = 480, 832
FRAMES, FPS = 49, 16
IMAGE_MODEL = "segmind/SSD-1B"
VIDEO_MODEL = "engineerA314/Wan2.1-Fun-V1.1-1.3B-InP-Diffusers"

STYLE = (
    "high-end 3D preschool animated movie, premium family animation, cute rounded shapes, "
    "soft cinematic lighting, rich colorful environment, expressive adorable face, polished stylized materials, "
    "gentle depth of field, appealing children's cartoon, consistent character design"
)
NEGATIVE = (
    "text, letters, subtitles, logo, watermark, blurry, low quality, duplicate character, extra limbs, "
    "deformed face, malformed hands, scary, horror, dark, photorealistic, flat vector art, sketch, "
    "character morphing, changing clothes, changing colors"
)


def ffmpeg(args):
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *map(str, args)])


def _tone(t, freq, attack=0.02, release=0.08):
    env = min(1.0, t / attack) * min(1.0, max(0.0, release / max(release, t)))
    return math.sin(2 * math.pi * freq * t) * env


def make_music(path: Path, seconds: float):
    """Create an original, lightweight preschool backing track locally.

    It uses only synthesized tones/no external samples, so the generated track does not depend on
    a music API or copyrighted audio asset. Melody, warm chords and a soft rhythmic pulse are mixed
    at a deliberately low level because Hindi narration is the foreground.
    """
    sr = 22050
    total = int(sr * seconds)
    # Four-bar loop: C, G, Am, F. Bright, simple and child-friendly.
    chords = [(261.63, 329.63, 392.00), (196.00, 246.94, 293.66),
              (220.00, 261.63, 329.63), (174.61, 220.00, 261.63)]
    melody = [523.25, 659.25, 783.99, 659.25, 587.33, 698.46, 880.00, 698.46]
    with wave.open(str(path), "w") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        for i in range(total):
            t = i / sr
            bar = int(t / 2.0) % 4
            beat = t * 2.0
            note = melody[int(beat) % len(melody)]
            note_t = t % 0.5
            sample = 0.0
            # Warm sustained chord bed.
            for f in chords[bar]:
                sample += 0.012 * math.sin(2 * math.pi * f * t)
            # Plucked melody, not a harsh continuous sine.
            sample += 0.020 * _tone(note_t, note, attack=0.015, release=0.28)
            # Soft kick on beats 1/3 and tiny shaker on off-beats.
            half = t % 1.0
            kick = math.exp(-32.0 * half) if half < 0.18 else 0.0
            sample += 0.010 * kick * math.sin(2 * math.pi * 95 * t)
            off = t % 0.25
            sample += 0.0035 * math.exp(-55.0 * off)
            # Smooth episode fade in/out.
            fade_in = min(1.0, t / 0.8)
            fade_out = min(1.0, max(0.0, seconds - t) / 1.2)
            sample *= fade_in * fade_out
            sample = max(-0.20, min(0.20, sample))
            left = int(sample * 32767)
            right = int((sample * 0.96) * 32767)
            wav.writeframes(left.to_bytes(2, "little", signed=True) + right.to_bytes(2, "little", signed=True))


async def make_voice(text, path):
    import edge_tts
    await edge_tts.Communicate(text or "", "hi-IN-SwaraNeural", rate="+4%", volume="+0%").save(str(path))


def character_prompt(story):
    return (
        f"Full-body character reference of {story.get('character', 'a cute little cartoon animal')}. "
        f"{STYLE}. Give the hero a simple memorable silhouette, large expressive eyes, clearly defined "
        "clothing/accessories, friendly preschool-safe appearance, consistent colors and proportions. "
        "Bright neutral storybook meadow, centered, full body visible, front three-quarter view, clean studio-like composition."
    )


def scene_prompt(story, scene, index):
    return (
        f"{story.get('character', 'cute cartoon animal')}. Scene {index}: {scene.get('visual', '')}. "
        f"{STYLE}. Preserve the exact same hero identity, face, fur/skin colors, clothes, accessories, "
        "body proportions and eye style from the reference image. Build the described environment around the hero. "
        "Show one clear readable action pose, natural staging, appealing foreground and background separation. "
        "No text or writing."
    )


def generate_anchors(story):
    print("🖼️ Loading Apache-2.0 SSD-1B image model...")
    pipe = AutoPipelineForText2Image.from_pretrained(
        IMAGE_MODEL, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    pipe.enable_model_cpu_offload()

    character_path = OUT / "character_reference.png"
    print("🧑‍🎨 Generating consistent character reference...")
    image = pipe(
        prompt=character_prompt(story),
        negative_prompt=NEGATIVE,
        height=768,
        width=512,
        num_inference_steps=4,
        guidance_scale=6.0,
        generator=torch.Generator(device="cpu").manual_seed(4242),
    ).images[0]
    image.save(character_path)

    # Build a fresh image-to-image pipeline instead of mutating the text-to-image pipeline.
    img2img = AutoPipelineForImage2Image.from_pretrained(
        IMAGE_MODEL, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    img2img.enable_model_cpu_offload()
    anchors = []
    for i, scene in enumerate(story["scenes"], start=1):
        out = OUT / f"anchor_{i:02d}.png"
        print(f"🖼️ AI scene anchor {i}/{len(story['scenes'])}...")
        result = img2img(
            prompt=scene_prompt(story, scene, i),
            negative_prompt=NEGATIVE,
            image=image,
            strength=0.48,
            height=768,
            width=512,
            num_inference_steps=4,
            guidance_scale=6.0,
            generator=torch.Generator(device="cpu").manual_seed(9000 + i),
        ).images[0]
        result = result.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        result.save(out)
        anchors.append(out)

    del img2img, pipe, image
    gc.collect()
    torch.cuda.empty_cache()
    return anchors


def generate_video(story, anchors):
    print("🎥 Loading Wan I2V — final expensive stage...")
    pipe = WanImageToVideoPipeline.from_pretrained(VIDEO_MODEL, torch_dtype=torch.float16)
    pipe.enable_sequential_cpu_offload()

    clips = []
    voices = []
    for i, (scene, anchor) in enumerate(zip(story["scenes"], anchors), start=1):
        raw = OUT / f"raw_{i:02d}.mp4"
        clip = OUT / f"clip_{i:02d}.mp4"
        voice = OUT / f"voice_{i:02d}.mp3"
        image = Image.open(anchor).convert("RGB")
        prompt = (
            f"{story.get('character', 'cute cartoon animal')}. {scene.get('visual', '')}. {STYLE}. "
            "Animate one clear main action only. Natural blinking, breathing, subtle ear/head/body movement, "
            "small paw/hand motion and gentle cinematic camera movement. Keep the exact hero identity, clothing, "
            "colors, proportions and background composition stable throughout the shot. No morphing, no new characters, no text."
        )
        print(f"🎬 Wan scene {i}/{len(story['scenes'])}...")
        with torch.inference_mode():
            result = pipe(
                image=image,
                prompt=prompt,
                negative_prompt=NEGATIVE,
                height=HEIGHT,
                width=WIDTH,
                num_frames=FRAMES,
                num_inference_steps=20,
                guidance_scale=5.0,
                generator=torch.Generator(device="cuda").manual_seed(12000 + i),
            )
        export_to_video(result.frames[0], str(raw), fps=FPS)
        ffmpeg([
            "-i", raw, "-vf", "scale=480:832:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", clip,
        ])
        asyncio.run(make_voice(scene.get("narration", ""), voice))
        clips.append(clip)
        voices.append(voice)
        del result, image
        torch.cuda.empty_cache()

    scene_final = []
    for clip, voice in zip(clips, voices):
        out = OUT / f"scene_final_{len(scene_final)+1:02d}.mp4"
        ffmpeg([
            "-i", clip, "-i", voice,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", out,
        ])
        scene_final.append(out)

    concat = OUT / "concat.txt"
    concat.write_text("".join(f"file '{p.name}'\n" for p in scene_final), encoding="utf-8")
    joined = OUT / "joined.mp4"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", joined])

    # Original local music; no external music asset/API and no copyright dependency.
    music = OUT / "kids_music.wav"
    music_seconds = len(scene_final) * FRAMES / FPS + 1.0
    make_music(music, music_seconds)
    final = OUT / "toon_kids_wan_i2v_v2.mp4"
    # Sidechain-compress music against narration so the melody ducks while the child hears the story.
    ffmpeg([
        "-i", joined, "-i", music,
        "-filter_complex",
        "[1:a]volume=0.75[music0];[music0][0:a]sidechaincompress=threshold=0.035:ratio=8:attack=20:release=300:makeup=1[bg];"
        "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", final,
    ])
    print(f"FINAL: {final}")
    print(f"SIZE: {final.stat().st_size}")
    return final


def main():
    if not torch.cuda.is_available():
        raise RuntimeError("Kaggle GPU is required")
    print("GPU:", torch.cuda.get_device_name(0))
    history = load_history()
    story = local_story(history)
    print("📖 Story:", story["title"])
    print("🎭 Character:", story.get("character", ""))
    anchors = generate_anchors(story)
    final = generate_video(story, anchors)
    (OUT / "story_used.txt").write_text(
        story["title"] + "\n" + story.get("moral", ""), encoding="utf-8"
    )
    print("DONE:", final)


if __name__ == "__main__":
    main()
