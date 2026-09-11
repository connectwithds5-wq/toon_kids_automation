"""Isolated Bytez text-to-video test for Toon Kids.

This file intentionally does not modify/import the production video pipeline.
It adds automatic model discovery + fallback so a stale/unavailable Bytez model
cannot stop the whole workflow.

Required secret: BYTEZ_API_KEY
Optional: GEMINI_API_KEY, BYTEZ_VIDEO_MODEL
"""

import base64
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
PREFERRED_MODEL = os.getenv("BYTEZ_VIDEO_MODEL", "Wan-AI/Wan2.1-T2V-1.3B").strip()
# Explicit fallbacks first; dynamic catalogue discovery is the final safety net.
FALLBACK_MODELS = [
    PREFERRED_MODEL,
    "Wan-AI/Wan2.1-T2V-1.3B",
    "ali-vilab/text-to-video-ms-1.7b",
]
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")

SCENE_SECONDS = 4
SCENE_COUNT = 4

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
The story must have simple action, a tiny discovery/problem, a happy payoff and a gentle moral feeling.
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
    if len(data.get("scenes", [])) != SCENE_COUNT:
        raise RuntimeError("Gemini did not return exactly 4 scenes")
    return data


def discover_t2v_models():
    """Ask Bytez for the current text-to-video catalogue.

    This prevents a hard-coded stale model ID from killing the workflow.
    Prefer small/free models, then fall back to any listed T2V model.
    """
    url = "https://api.bytez.com/models/v2/list/models"
    r = requests.get(
        url,
        params={"task": "text-to-video"},
        headers={"Authorization": BYTEZ_KEY},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"⚠️ Bytez model catalogue unavailable: HTTP {r.status_code}; using explicit fallbacks")
        return []

    data = r.json()
    models = data.get("output", []) if isinstance(data, dict) else []
    result = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = item.get("modelId")
        if not model_id:
            continue
        result.append(item)

    # Prefer free/small models because this test is intended to conserve credits.
    result.sort(key=lambda m: (
        0 if str(m.get("meter", "")).lower().endswith("free") else 1,
        float(m.get("params", 9999) or 9999),
    ))
    return result


def build_model_candidates():
    candidates = []
    for model in FALLBACK_MODELS:
        if model and model not in candidates:
            candidates.append(model)

    try:
        catalogue = discover_t2v_models()
        # First add catalogue models <= 7B, then any remaining T2V models.
        for item in catalogue:
            model = item.get("modelId")
            params = float(item.get("params", 9999) or 9999)
            if model and params <= 7 and model not in candidates:
                candidates.append(model)
        for item in catalogue:
            model = item.get("modelId")
            if model and model not in candidates:
                candidates.append(model)
    except Exception as exc:
        print(f"⚠️ Could not inspect Bytez catalogue: {exc}")

    print("🔁 Bytez model fallback chain:")
    for i, model in enumerate(candidates, 1):
        print(f"   {i}. {model}")
    return candidates


def extract_video_output(data, index):
    output = data.get("output", data) if isinstance(data, dict) else data

    # Some Bytez T2V versions return base64 MP4 bytes.
    if isinstance(output, dict):
        for key in ("output_mp4", "base64", "video_base64"):
            value = output.get(key)
            if isinstance(value, str) and len(value) > 1000:
                try:
                    path = WORK / f"bytez_scene_{index + 1:02d}.mp4"
                    path.write_bytes(base64.b64decode(value))
                    if path.stat().st_size >= 10_000:
                        return path
                except Exception:
                    pass

    if isinstance(data, dict):
        for key in ("output_mp4", "base64", "video_base64"):
            value = data.get(key)
            if isinstance(value, str) and len(value) > 1000:
                try:
                    path = WORK / f"bytez_scene_{index + 1:02d}.mp4"
                    path.write_bytes(base64.b64decode(value))
                    if path.stat().st_size >= 10_000:
                        return path
                except Exception:
                    pass

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
    raise RuntimeError(f"Bytez returned no usable video output. Response keys: {list(data)[:20] if isinstance(data, dict) else type(data)}")


def bytez_video(prompt, index, models):
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

    last_error = None
    for model in models:
        url = f"https://api.bytez.com/models/v2/{model}"
        print(f"🎬 Scene {index + 1}/{SCENE_COUNT} → trying {model}")

        for attempt in range(2):
            try:
                response = requests.post(
                    url,
                    headers={"Authorization": BYTEZ_KEY, "Content-Type": "application/json"},
                    json={"text": full_prompt},
                    timeout=300,
                )

                if response.status_code in (401, 403):
                    raise RuntimeError("Bytez API key rejected (401/403). Check BYTEZ_API_KEY.")

                if response.status_code in (404, 400):
                    raise RuntimeError(f"model unavailable: HTTP {response.status_code}")

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == 0:
                        print(f"   ⚠️ transient HTTP {response.status_code}; retrying once...")
                        time.sleep(4)
                        continue
                    raise RuntimeError(f"transient HTTP {response.status_code}")

                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and data.get("error"):
                    raise RuntimeError(f"provider error: {data.get('error')}")
                return extract_video_output(data, index), model

            except Exception as exc:
                last_error = exc
                print(f"   ❌ {model}: {exc}")
                break

        print("   ↪️ Switching automatically to next model...")

    raise RuntimeError(f"All Bytez video models failed. Last error: {last_error}")


def download(url, path):
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    path.write_bytes(r.content)
    if path.stat().st_size < 10_000:
        raise RuntimeError(f"Downloaded video looks invalid: {path}")


def make_vertical(src, dst):
    run_ffmpeg([
        "-i", str(src),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
        "-t", str(SCENE_SECONDS), "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dst),
    ])


def concat(scene_paths):
    concat_file = WORK / "concat.txt"
    concat_file.write_text("".join(f"file '{p.resolve()}'\n" for p in scene_paths), encoding="utf-8")
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart", str(OUT),
    ])


def main():
    print("==========================================")
    print("TOON KIDS — BYTEZ VIDEO TEST + FALLBACK")
    print("==========================================")
    print(f"Preferred model: {PREFERRED_MODEL}")
    print(f"Output: {OUT}")

    if not BYTEZ_KEY:
        raise SystemExit("❌ Add BYTEZ_API_KEY to GitHub Actions secrets before running this test.")

    for p in WORK.glob("*"):
        if p.is_file():
            p.unlink()

    models = build_model_candidates()
    if not models:
        raise RuntimeError("No Bytez text-to-video models were discovered.")

    story = gemini_story()
    print(f"📖 Story: {story.get('title', 'Bytez Toon Test')}")

    scene_paths = []
    used_models = []
    active_models = models

    for i, scene in enumerate(story["scenes"]):
        result, used_model = bytez_video(scene.get("visual", "cute bunny moves happily"), i, active_models)
        used_models.append(used_model)
        # Once a model works, keep using it first for character consistency.
        active_models = [used_model] + [m for m in models if m != used_model]

        if isinstance(result, Path):
            raw = result
        else:
            raw = WORK / f"bytez_raw_{i+1:02d}.mp4"
            download(result, raw)

        final = WORK / f"scene_{i+1:02d}.mp4"
        make_vertical(raw, final)
        scene_paths.append(final)

    concat(scene_paths)
    metadata = {
        "title": story.get("title", ""),
        "preferred_model": PREFERRED_MODEL,
        "models_attempted": models,
        "models_used_by_scene": used_models,
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
    print(f"🤖 Models used: {used_models}")


if __name__ == "__main__":
    main()
