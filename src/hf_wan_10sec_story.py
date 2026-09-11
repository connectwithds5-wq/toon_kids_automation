import os
import shutil
import subprocess
from pathlib import Path

from gradio_client import Client

from toon_kids_story import WORK, local_story, load_history
from nursery_rhyme import local_rhyme

# IMPORTANT: this is the actual Wan 2.2 14B T2V Space.
# It takes TEXT only. No anchor image, Gemini, Z-Image or I2V is used.
SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti")
HF_TOKEN = os.getenv("HF_TOKEN") or None
CONTENT_MODE = os.getenv("CONTENT_MODE", "story").lower()
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_10sec_story.mp4"))
CLIP_SECONDS = 3.5
FINAL_SECONDS = 10.0
WAN_STEPS = int(os.getenv("WAN_STEPS", "4"))
WAN_GUIDANCE = float(os.getenv("WAN_GUIDANCE", "1.0"))
WAN_GUIDANCE_2 = float(os.getenv("WAN_GUIDANCE_2", "3.0"))


def extract_video_path(result):
    if isinstance(result, dict):
        for key in ("video", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"No video path in Wan result: {result!r}")
    if isinstance(result, (tuple, list)):
        for item in result:
            if isinstance(item, str) and (item.endswith((".mp4", ".webm", ".mov", ".mkv")) or Path(item).is_file()):
                return item
            try:
                return extract_video_path(item)
            except RuntimeError:
                pass
        raise RuntimeError(f"No video path in Wan result: {result!r}")
    if isinstance(result, str) and result:
        return result
    raise RuntimeError(f"Unsupported Wan result: {result!r}")


def make_clip(client, story, scene, index):
    clip_path = WORK / f"wan_10sec_scene_{index + 1}.mp4"
    character = story.get("character", "cute animated animal")
    prompt = (
        "Premium high-end 3D CGI children's animated musical feature film. "
        f"Main character: {character}. "
        f"Story action: {scene.get('visual', '')}. "
        f"Camera: {scene.get('camera', 'smooth cinematic tracking shot')}. "
        "Generate the complete scene directly from this text as dimensional CGI animation. "
        "Cute expressive character, polished studio rendering, detailed materials/fur, volumetric lighting, "
        "cinematic rim light, realistic shadows, depth of field, optical bokeh, atmospheric perspective, "
        "filmic color grading, smooth physically believable motion and clear foreground/midground/background depth. "
        "Joyful nursery-rhyme energy, child-friendly premium animation. No text, subtitles, letters, logo or watermark."
    )[:1500]
    negative_prompt = (
        "flat vector art, 2D illustration, sticker, emoji, clip-art, worksheet, flat cartoon, flat fills, "
        "ink outlines, poster, cel-shaded illustration, blurry, low quality, distorted face, deformed body, "
        "extra limbs, missing limbs, bad anatomy, duplicate character, morphing, face morphing, flicker, jitter, "
        "frame tearing, unstable colors, text, subtitles, logo, watermark, gray frame, noise"
    )

    print(f"[Scene {index + 1}/3] Wan 2.2 14B T2V — {CLIP_SECONDS}s")
    result = client.predict(
        prompt,
        negative_prompt,
        CLIP_SECONDS,
        WAN_GUIDANCE,
        WAN_GUIDANCE_2,
        WAN_STEPS,
        1000 + index,
        False,
        api_name="/generate_video",
    )
    source = Path(extract_video_path(result))
    if not source.is_file():
        raise FileNotFoundError(f"Wan 2.2 video does not exist: {source}")
    shutil.copy2(source, clip_path)
    return clip_path


def concat_and_trim(clips):
    concat_file = WORK / "wan_10sec_concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clips), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-t", str(FINAL_SECONDS), "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT),
    ]
    print("Assembling the 10-second Wan 2.2 T2V video...")
    subprocess.run(cmd, check=True)


def main():
    WORK.mkdir(exist_ok=True)
    history = load_history()
    is_rhyme = CONTENT_MODE in {"rhyme", "nursery_rhyme", "nursery-rhyme"}
    story = local_rhyme(history) if is_rhyme else local_story(history)
    scenes = story.get("scenes", [])[:3]
    if len(scenes) < 3:
        raise RuntimeError("The selected content must contain at least 3 scenes.")

    print(f"Content mode: {CONTENT_MODE}")
    print(f"Title: {story['title']}")
    print("Plan: 3 Wan 2.2 T2V scenes x 3.5s, exact 10s final video.")
    print(f"HF_TOKEN configured: {'yes' if HF_TOKEN else 'no (anonymous ZeroGPU)'}")
    print(f"ENGINE: {SPACE} — Wan 2.2 14B T2V ONLY")
    print("No image generation stage is used.")

    client = Client(SPACE, token=HF_TOKEN) if HF_TOKEN else Client(SPACE)
    clips = [make_clip(client, story, scene, i) for i, scene in enumerate(scenes)]
    concat_and_trim(clips)
    subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
        "-of", "default=noprint_wrappers=1", str(OUT)
    ], check=True)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
