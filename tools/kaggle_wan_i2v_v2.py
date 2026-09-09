import asyncio
import math
import subprocess
import sys
import wave
from pathlib import Path

# V2 production pipeline:
# story -> AI-generated character/scene anchors (SSD-1B, Apache-2.0)
# -> Wan I2V -> Hindi TTS -> music -> 9:16 episode.
# No paid image/video API is required.

subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "diffusers>=0.36.0", "transformers>=4.49.0", "accelerate>=1.5.0",
    "safetensors", "imageio[ffmpeg]", "edge-tts", "pillow",
])

import gc
import torch
from PIL import Image
from diffusers import AutoPipelineForText2Image, AutoPipelineForImage2Image
from diffusers import WanImageToVideoPipeline
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
    "high-end 3D preschool animated movie, polished family animation, cute rounded shapes, "
    "soft cinematic lighting, rich colorful environment, expressive adorable face, clean stylized materials, "
    "subtle depth of field, premium children's cartoon, consistent character design"
)
NEGATIVE = (
    "text, letters, subtitles, logo, watermark, blurry, low quality, duplicate character, extra limbs, "
    "deformed face, malformed hands, scary, horror, dark, photorealistic, flat vector art, sketch"
)


def ffmpeg(args):
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *map(str, args)])


def make_music(path: Path, seconds: float):
    sr = 22050
    notes = [523.25, 659.25, 783.99, 659.25, 587.33, 698.46, 880.0, 698.46]
    total = int(sr * seconds)
    with wave.open(str(path), "w") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sr)
        for i in range(total):
            t = i / sr
            f = notes[int(t * 4) % len(notes)]
            env = min(1.0, t * 4) * min(1.0, max(0.0, seconds - t) * 2)
            value = (0.028 * math.sin(2 * math.pi * f * t) + 0.012 * math.sin(2 * math.pi * f * 2 * t)) * env
            wav.writeframes(int(max(-1, min(1, value)) * 32767).to_bytes(2, "little", signed=True))


async def make_voice(text, path):
    import edge_tts
    await edge_tts.Communicate(text, "hi-IN-SwaraNeural", rate="+6%", volume="+0%").save(str(path))


def character_prompt(story):
    return (
        f"Full-body character reference of {story.get('character', 'a cute little cartoon animal')}. "
        f"{STYLE}. The character must have a simple memorable silhouette, large expressive eyes, "
        "clearly defined clothing/accessories, child-safe friendly appearance, standing in a bright neutral "
        "storybook meadow, centered, full body visible, front three-quarter view."
    )


def scene_prompt(story, scene, index):
    return (
        f"{story.get('character', 'cute cartoon animal')}. "
        f"Scene {index}: {scene.get('visual', '')}. "
        f"{STYLE}. Preserve the exact same character identity, face, fur/skin colors, clothes, accessories, "
        "body proportions and eye style from the reference image. Place the character naturally inside the "
        "described environment. Show a clear readable action pose with one main action only. "
        "Leave clean space around the character. No text or writing."
    )


def generate_anchors(story):
    print("🖼️ Loading Apache-2.0 SSD-1B image model...")
    pipe = AutoPipelineForText2Image.from_pretrained(
        IMAGE_MODEL, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    pipe.enable_model_cpu_offload()

    character_path = OUT / "character_reference.png"
    print("🧑‍🎨 Generating one consistent character reference...")
    image = pipe(
        prompt=character_prompt(story),
        negative_prompt=NEGATIVE,
        height=768,
        width=512,
        num_inference_steps=4,
        guidance_scale=6.0,
        generator=torch.Generator(device="cpu").manual_seed(4242),
    ).images[0]
    image.save(character_path, quality=96)

    img2img = AutoPipelineForImage2Image.from_pipe(pipe)
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
        # Crop/resize to the exact portrait area expected by the video pipeline.
        result = result.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        result.save(out, quality=96)
        anchors.append(out)

    del img2img, pipe, image
    gc.collect(); torch.cuda.empty_cache()
    return anchors


def generate_video(story, anchors):
    print("🎥 Loading Wan I2V...")
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
            "Animate only the described action: natural blinking, subtle breathing, ear/head/body movement, "
            "small hand or paw movement and gentle camera motion. Keep identity, clothing, colors, proportions "
            "and background composition stable. Do not morph the character. No text."
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
            "-i", raw,
            "-vf", "scale=480:832:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", clip,
        ])
        asyncio.run(make_voice(scene.get("narration", ""), voice))
        clips.append(clip); voices.append(voice)
        del result, image
        torch.cuda.empty_cache()

    scene_final = []
    for i, (clip, voice) in enumerate(zip(clips, voices), start=1):
        out = OUT / f"scene_final_{i:02d}.mp4"
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

    music = OUT / "kids_music.wav"
    make_music(music, len(scene_final) * FRAMES / FPS + 1)
    final = OUT / "toon_kids_wan_i2v_v2.mp4"
    ffmpeg([
        "-i", joined, "-i", music,
        "-filter_complex", "[1:a]volume=0.09[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v:0", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", final,
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
    # Keep the selected story available to the workflow for debugging/audit.
    (OUT / "story_used.txt").write_text(story["title"] + "\n" + story.get("moral", ""), encoding="utf-8")
    print("DONE:", final)


if __name__ == "__main__":
    main()
