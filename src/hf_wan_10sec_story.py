import os
import shutil
import subprocess
from pathlib import Path

from gradio_client import Client, handle_file

from toon_kids_story import WORK, local_story, load_history, scene_image

SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_10sec_story.mp4"))
CLIP_SECONDS = 3.5
FINAL_SECONDS = 10.0


def extract_video_path(result):
    if isinstance(result, dict):
        for key in ("video", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"No video path in HF result: {result!r}")

    if isinstance(result, (tuple, list)):
        for item in result:
            if isinstance(item, str) and (item.endswith((".mp4", ".webm", ".mov", ".mkv")) or Path(item).is_file()):
                return item
            try:
                return extract_video_path(item)
            except RuntimeError:
                pass
        raise RuntimeError(f"No video path in HF result: {result!r}")

    if isinstance(result, str) and result:
        return result
    raise RuntimeError(f"Unsupported HF result: {result!r}")


def make_clip(client, story, scene, index):
    image_path = WORK / f"wan_10sec_scene_{index + 1}.png"
    clip_path = WORK / f"wan_10sec_scene_{index + 1}.mp4"

    print(f"[Scene {index + 1}/3] Creating anchor image...")
    scene_image(story, scene, index, image_path)

    prompt = (
        "High quality 3D cartoon children's animation. Keep the EXACT same main character "
        "design, colors, clothes, face and proportions as the input image. "
        f"Character: {story.get('character', 'cute cartoon animal')}. "
        f"Scene action: {scene.get('visual', '')}. "
        f"Camera: {scene.get('camera', 'gentle cinematic movement')}. "
        "Cute expressive movement, natural body motion, stable face, stable anatomy, "
        "smooth cinematic animation, bright colorful children's movie look, "
        "clean background, no text, no letters, no subtitles, no logo, no watermark."
    )[:900]

    negative_prompt = (
        "blurry, low quality, out of focus, distorted face, deformed body, extra limbs, "
        "missing limbs, bad anatomy, duplicate character, character morphing, face morphing, "
        "flicker, jitter, frame tearing, unstable clothing, unstable colors, text, letters, "
        "subtitles, logo, watermark, rectangle artifact, gray frame, noisy image"
    )

    print(f"[Scene {index + 1}/3] Generating {CLIP_SECONDS}s Wan 2.2 clip...")
    result = client.predict(
        handle_file(str(image_path)),
        prompt,
        6,
        negative_prompt,
        CLIP_SECONDS,
        1.0,
        1.0,
        1000 + index,
        False,
        api_name="/generate_video",
    )

    source = Path(extract_video_path(result))
    if not source.is_file():
        raise FileNotFoundError(f"HF video does not exist: {source}")
    shutil.copy2(source, clip_path)
    return clip_path


def concat_and_trim(clips):
    concat_file = WORK / "wan_10sec_concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clips), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-t", str(FINAL_SECONDS),
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT),
    ]
    print("Assembling the 10-second story...")
    subprocess.run(cmd, check=True)


def main():
    WORK.mkdir(exist_ok=True)
    story = local_story(load_history())
    scenes = story.get("scenes", [])[:3]
    if len(scenes) < 3:
        raise RuntimeError("The selected story must contain at least 3 scenes.")

    print(f"Story: {story['title']}")
    print("Plan: 3 story scenes x 3.5s, then trim to exactly 10s.")
    client = Client(SPACE, token=HF_TOKEN)
    clips = [make_clip(client, story, scene, i) for i, scene in enumerate(scenes)]
    concat_and_trim(clips)

    subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
        "-of", "default=noprint_wrappers=1", str(OUT)
    ], check=True)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
