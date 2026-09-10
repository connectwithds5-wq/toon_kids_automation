import asyncio
import math
import subprocess
import sys
import wave
from pathlib import Path

# Production target: a short, story-driven 9:16 kids episode.
# Story engine -> deterministic scene-specific anchors -> Wan I2V -> Hindi TTS -> music.

subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "diffusers>=0.36.0", "transformers>=4.49.0", "accelerate>=1.5.0",
    "imageio[ffmpeg]", "edge-tts", "pillow",
    "google-genai", "google-api-python-client", "google-auth",
])

import torch
from PIL import Image
from diffusers import WanImageToVideoPipeline
from diffusers.utils import export_to_video

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from toon_kids_story import local_story, load_history, scene_image  # noqa: E402

OUT = Path("/kaggle/working")
FPS = 16
FRAMES = 49
MODEL_WIDTH, MODEL_HEIGHT = 832, 480
MODEL_ID = "engineerA314/Wan2.1-Fun-V1.1-1.3B-InP-Diffusers"

STYLE = (
    "premium preschool 3D cartoon animation, polished family animation, cute rounded characters, "
    "bright cheerful colors, soft cinematic lighting, expressive eyes, clean shapes, "
    "gentle depth of field, playful magical atmosphere"
)
NEGATIVE = (
    "blurry, low quality, flicker, jitter, frozen image, deformed face, distorted anatomy, "
    "extra limbs, duplicate characters, identity change, clothing change, color change, "
    "text, subtitles, letters, logo, watermark, scary, horror, dark scene"
)


def ffmpeg(args):
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args])


async def make_voice(text: str, path: Path):
    import edge_tts
    await edge_tts.Communicate(text or "", "hi-IN-MadhurNeural", rate="+6%", volume="+0%").save(str(path))


def make_music(path: Path, seconds: float):
    sr = 22050
    notes = [523.25, 659.25, 783.99, 659.25, 587.33, 698.46, 880.0, 698.46]
    total = int(sr * seconds)
    with wave.open(str(path), "w") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sr)
        for i in range(total):
            t = i / sr
            f = notes[int(t * 4) % len(notes)]
            env = min(1.0, t * 3.0) * min(1.0, max(0.0, seconds - t) * 2.0)
            value = (0.028 * math.sin(2 * math.pi * f * t) + 0.012 * math.sin(4 * math.pi * f * t)) * env
            wav.writeframes(int(max(-1, min(1, value)) * 32767).to_bytes(2, "little", signed=True))


def main():
    if not torch.cuda.is_available():
        raise RuntimeError("Kaggle did not provide a CUDA GPU")
    print("GPU:", torch.cuda.get_device_name(0))

    history = load_history()
    story = local_story(history)
    scenes = story.get("scenes", [])[:7]
    if not scenes:
        raise RuntimeError("Story has no scenes")
    print(f"Episode: {story['title']} | scenes={len(scenes)}")

    pipe = WanImageToVideoPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float16)
    pipe.enable_sequential_cpu_offload()

    videos, voices = [], []
    for i, scene in enumerate(scenes):
        idx = i + 1
        anchor = OUT / f"anchor_{idx:02d}.png"
        raw = OUT / f"raw_{idx:02d}.mp4"
        portrait = OUT / f"scene_{idx:02d}.mp4"
        voice = OUT / f"voice_{idx:02d}.mp3"

        # Every scene gets a different deterministic anchor from the story engine.
        scene_image(story, scene, i, anchor)
        portrait_img = Image.open(anchor).convert("RGB")
        model_img = portrait_img.rotate(90, expand=True).resize((MODEL_WIDTH, MODEL_HEIGHT), Image.LANCZOS)

        action = scene.get("visual", "")
        camera = scene.get("camera", "gentle camera movement")
        prompt = (
            f"{STYLE}. Main character: {story.get('character', 'cute cartoon animal')}. "
            f"Scene action: {action}. Camera: {camera}. "
            "Use the input image as the exact visual identity reference. Keep face, body proportions, "
            "outfit, colors and art style stable. Animate a clear beginning-to-end action: "
            "anticipation, one simple physical action, then a natural settle. Add subtle blinking, "
            "ear/head/body movement and environmental motion. Do not invent new characters or objects."
        )[:900]

        print(f"Generating scene {idx}/{len(scenes)}...")
        with torch.inference_mode():
            result = pipe(
                image=model_img,
                prompt=prompt,
                negative_prompt=NEGATIVE,
                height=MODEL_HEIGHT,
                width=MODEL_WIDTH,
                num_frames=FRAMES,
                num_inference_steps=24,
                guidance_scale=5.0,
                generator=torch.Generator(device="cuda").manual_seed(9000 + idx),
            )
        export_to_video(result.frames[0], str(raw), fps=FPS)
        ffmpeg([
            "-i", str(raw), "-vf", "transpose=2,scale=480:832:flags=lanczos",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-pix_fmt", "yuv420p", "-an", str(portrait),
        ])
        asyncio.run(make_voice(scene.get("narration", ""), voice))
        videos.append(portrait); voices.append(voice)
        del result, model_img, portrait_img
        torch.cuda.empty_cache()

    final_scenes = []
    for i, (video, voice) in enumerate(zip(videos, voices), start=1):
        out = OUT / f"scene_audio_{i:02d}.mp4"
        ffmpeg([
            "-i", str(video), "-i", str(voice),
            "-filter_complex", "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]",
            "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "128k", "-shortest", str(out),
        ])
        final_scenes.append(out)

    concat = OUT / "concat.txt"
    concat.write_text("\n".join(f"file '{p.name}'" for p in final_scenes), encoding="utf-8")
    joined = OUT / "joined.mp4"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])

    seconds = len(final_scenes) * (FRAMES / FPS)
    music = OUT / "kids_music.wav"
    make_music(music, seconds + 1)
    final = OUT / "toon_kids_wan_i2v_episode.mp4"
    ffmpeg([
        "-i", str(joined), "-i", str(music),
        "-filter_complex", "[1:a]volume=0.07[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v:0", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final),
    ])
    print(f"FINAL: {final}")
    print(f"DURATION_TARGET: {seconds:.1f}s")
    print(f"SIZE: {final.stat().st_size}")


if __name__ == "__main__":
    main()
