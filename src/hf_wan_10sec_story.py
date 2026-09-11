import os
import shutil
import subprocess
from pathlib import Path

from gradio_client import Client

from toon_kids_story import WORK, local_story, load_history
from nursery_rhyme import local_rhyme

# Proven fast Wan 2.2 ZeroGPU Space, using TEXT-TO-VIDEO only.
# No anchor image, Z-Image, Gemini, or image-to-video stage.
SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None
CONTENT_MODE = os.getenv("CONTENT_MODE", "story").lower()
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_10sec_story.mp4"))
CLIP_SECONDS = 3.5
FINAL_SECONDS = 10.0
WAN_STEPS = int(os.getenv("WAN_STEPS", "6"))
WAN_CFG = float(os.getenv("WAN_CFG", "1.0"))
WAN_SHIFT = float(os.getenv("WAN_SHIFT", "1.0"))


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


def is_quota_error(exc):
    text = str(exc).lower()
    return any(x in text for x in ("zerogpu quota", "quota exceeded", "0s left"))


def make_clip(client, story, scene, index):
    clip_path = WORK / f"wan_10sec_scene_{index + 1}.mp4"
    character = story.get("character", "cute animated animal")
    prompt = (
        "Premium high-end 3D CGI children's animated musical feature film. "
        f"Main character: {character}. "
        f"Action: {scene.get('visual', '')}. "
        f"Camera: {scene.get('camera', 'smooth cinematic tracking shot')}. "
        "Create the scene directly from text as a fully rendered dimensional 3D animation. "
        "Cute expressive character, polished studio CGI, detailed materials and fur, realistic lighting, "
        "volumetric light, cinematic depth of field, optical bokeh, realistic shadows, filmic color grading, "
        "smooth physically believable movement, clear foreground and background depth, joyful nursery-rhyme energy. "
        "Keep the character design coherent throughout the shot. No text, subtitles, letters, logo or watermark."
    )[:1200]
    negative_prompt = (
        "flat vector art, 2D illustration, sticker, emoji, clip-art, worksheet, flat cartoon, flat fills, "
        "ink outlines, poster, cel-shaded illustration, blurry, low quality, distorted face, deformed body, "
        "extra limbs, missing limbs, bad anatomy, duplicate character, morphing, face morphing, flicker, jitter, "
        "frame tearing, unstable colors, text, subtitles, logo, watermark, gray frame, noise"
    )

    print(f"[Scene {index + 1}/3] Wan 2.2 T2V — {CLIP_SECONDS}s")
    result = client.predict(
        prompt,
        negative_prompt,
        WAN_STEPS,
        CLIP_SECONDS,
        WAN_CFG,
        WAN_SHIFT,
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
    print("ENGINE: Wan 2.2 T2V ONLY — no image generation.")

    client = Client(SPACE, token=HF_TOKEN) if HF_TOKEN else Client(SPACE)
    clips = []
    for index, scene in enumerate(scenes):
        try:
            clips.append(make_clip(client, story, scene, index))
        except Exception as exc:
            if HF_TOKEN and is_quota_error(exc):
                print("[Wan fallback] Authenticated ZeroGPU quota exhausted; retrying anonymously...")
                client = Client(SPACE)
                clips.append(make_clip(client, story, scene, index))
            else:
                raise

    concat_and_trim(clips)
    subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
        "-of", "default=noprint_wrappers=1", str(OUT)
    ], check=True)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
