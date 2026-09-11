"""Isolated Bytez text-to-video test for Toon Kids.

This file intentionally does not modify/import the production video pipeline.
It generates a short 4-scene Hindi toon story with Bytez T2V, adds optional
Edge-TTS narration, and assembles a vertical MP4 with FFmpeg.

Required secret: BYTEZ_API_KEY
Optional: GEMINI_API_KEY (story planning), BYTEZ_VIDEO_MODEL,
UPLOAD_YOUTUBE=false (default).
"""

import json
import os
import subprocess
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
WORK = BASE / "work_bytez_toon"
WORK.mkdir(exist_ok=True)
OUT = BASE / os.getenv("BYTEZ_OUTPUT", "bytez_toon_story_test.mp4")
META = BASE / "bytez_toon_story_metadata.json"

BYTEZ_KEY = os.getenv("BYTEZ_API_KEY", "").strip()
BYTEZ_MODEL = os.getenv("BYTEZ_VIDEO_MODEL", "ali-vilab/text-to-video-ms-1.7b").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")

# Bytez's documented text-to-video endpoint accepts {"text": prompt}.
BYTEZ_URL = f"https://api.bytez.com/models/v2/{BYTEZ_MODEL}"

SCENE_SECONDS = 4
SCENE_COUNT = 4
WIDTH = 1080
HEIGHT = 1920

CHARACTER = (
    "one adorable small white bunny, round fluffy face, big blue eyes, long upright white ears "
    "with pink inner ears, tiny pink nose, rosy cheeks, royal-blue overalls, bright yellow bow tie, "
    "tiny brown shoes, consistent character design"
)
WORLD = (
    "a sunny magical cartoon garden with green grass, colorful flowers, apple trees, soft hills, "
    "warm golden daylight, polished 3D children's animation"
)
NEGATIVE = (
    "text, letters, numbers, subtitles, logo, watermark, duplicate character, extra limbs, distorted face, "
    "flicker, jitter, blurry, cropped character, dark mood, horror, realistic human"
)


def run_ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def gemini_story():
    """Use Gemini only for a small story plan; Bytez remains the video provider."""
    if not GEMINI_KEY:
        return {
            "title": "खरगोश और जादुई सेब",
            "scenes": [
                {"narration": "एक नन्हा खरगोश बगीचे में चमकता सेब देखता है।", "visual": "bunny happily discovers one glowing red apple"},
                {"narration": "वह सेब को टोकरी में रखता है और खुशी से उछलता है।", "visual": "bunny gently places apples into a little basket and claps"},
                {"narration": "अचानक पेड़ से और रंगीन सेब टपकने लगते हैं।", "visual": "several colorful apples bounce playfully from the tree"},
                {"narration": "खरगोश मुस्कुराता है और सबके साथ सेब बाँटता है।", "visual": "bunny celebrates and shares apples in a joyful garden finale"},
            ],
        }

    from google import genai
    from google.genai import types

    prompt = f"""
Create an ORIGINAL Hindi preschool toon story for a 16-second vertical short.
Exactly 4 scenes, 4 seconds each. One consistent character and world.
Character: {CHARACTER}
World: {WORLD}
The story must have simple action, a tiny problem/discovery, a happy payoff and a gentle moral feeling.
Do not use existing songs, characters, channel names or copyrighted wording.
Return JSON only: {{"title":"...","scenes":[{{"narration":"...","visual":"..."}} x4]}}
"""
    client = genai.Client(api_key=GEMINI_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    data = json.loads(response.text)
    scenes = data.get("scenes", [])
    if len(scenes) != SCENE_COUNT:
        raise RuntimeError(f"Gemini returned {len(scenes)} scenes; expected {SCENE_COUNT}")
    return data


def bytez_video(prompt, index):
    if not BYTEZ_KEY:
        raise RuntimeError("BYTEZ_API_KEY secret is required")

    full_prompt = (
        "Premium polished 3D preschool cartoon animation. Vertical 9:16 composition. "
        f"FIXED CHARACTER: {CHARACTER}. FIXED WORLD: {WORLD}. "
        f"ACTION: {prompt}. "
        "Joyful expressive acting, smooth readable movement, gentle cinematic camera, rich colors, "
        "soft depth of field, clear silhouette, no scene cuts. "
        f"NEGATIVE: {NEGATIVE}."
    )
    print(f"🎬 Bytez scene {index + 1}/{SCENE_COUNT} using {BYTEZ_MODEL}")
    response = requests.post(
        BYTEZ_URL,
        headers={"Authorization": BYTEZ_KEY, "Content-Type": "application/json"},
        json={"text": full_prompt},
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    output = data.get("output", data)

    # Bytez models can return a URL directly or nested in common response shapes.
    candidates = []
    if isinstance(output, str):
        candidates.append(output)
    if isinstance(output, dict):
        for key in ("url", "video_url", "media_url", "download_url"):
            if isinstance(output.get(key), str):
                candidates.append(output[key])
    if isinstance(data, dict):
        for key in ("url", "video_url", "media_url", "download_url"):
            if isinstance(data.get(key), str):
                candidates.append(data[key])

    for url in candidates:
        if url.startswith("http"):
            return url
    raise RuntimeError(f"Bytez returned no video URL. Response keys: {list(data)[:20]}")


def download(url, path):
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    path.write_bytes(r.content)
    if path.stat().st_size < 10_000:
        raise RuntimeError(f"Downloaded video looks invalid: {path}")


def make_vertical(src, dst):
    # Scale to fill 1080x1920 without stretching; crop only if the provider returns another ratio.
    run_ffmpeg([
        "-i", str(src), "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
        "-t", str(SCENE_SECONDS), "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dst)
    ])


def concat(scene_paths):
    concat_file = WORK / "concat.txt"
    concat_file.write_text("".join(f"file '{p.resolve()}'\n" for p in scene_paths), encoding="utf-8")
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart", str(OUT)
    ])


def main():
    print("==========================================")
    print("TOON KIDS — ISOLATED BYTEZ VIDEO TEST")
    print("==========================================")
    print(f"Model: {BYTEZ_MODEL}")
    print(f"Output: {OUT}")

    if not BYTEZ_KEY:
        raise SystemExit("❌ Add BYTEZ_API_KEY to GitHub Actions secrets before running this test.")

    for p in WORK.glob("*"):
        if p.is_file():
            p.unlink()

    story = gemini_story()
    print(f"📖 Story: {story.get('title', 'Bytez Toon Test')}")

    scene_paths = []
    for i, scene in enumerate(story["scenes"]):
        raw = WORK / f"bytez_raw_{i+1:02d}.mp4"
        final = WORK / f"scene_{i+1:02d}.mp4"
        url = bytez_video(scene.get("visual", "cute bunny moves happily"), i)
        download(url, raw)
        make_vertical(raw, final)
        scene_paths.append(final)

    concat(scene_paths)
    metadata = {
        "title": story.get("title", ""),
        "model": BYTEZ_MODEL,
        "scene_count": SCENE_COUNT,
        "scene_seconds": SCENE_SECONDS,
        "duration_target_seconds": SCENE_COUNT * SCENE_SECONDS,
        "provider": "bytez",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "youtube_upload": False,
    }
    META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✅ BYTEZ TOON TEST COMPLETE")
    print(f"🎥 {OUT}")


if __name__ == "__main__":
    main()
