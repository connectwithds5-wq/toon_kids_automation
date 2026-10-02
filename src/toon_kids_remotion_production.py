import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from toon_kids_story import (
    HISTORY,
    META,
    OUT,
    RUN_SLOT,
    SCENE_COUNT,
    SCENE_SECONDS,
    WORK,
    TEXT_MODEL,
    genai,
    is_duplicate,
    choose_topic,
    make_story,
    local_story,
    load_history,
    save_history,
    make_tts_sync,
    scene_image,
    story_text,
    norm,
    upload_youtube,
)

BASE = Path(__file__).resolve().parent.parent
REMOTION_DIR = BASE / "remotion-kids"
PUBLIC_DIR = REMOTION_DIR / "public" / "content" / "kids"
IMAGES_DIR = PUBLIC_DIR / "images"
AUDIO_DIR = PUBLIC_DIR / "audio"

def prepare_assets(story):
    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    for i, scene in enumerate(story["scenes"], start=1):
        image_path = WORK / f"scene_art_{i:02d}.png"
        audio_path = WORK / f"tts_{i:02d}.mp3"

        print(f"🎨 Drawing scene {i}/{SCENE_COUNT}")
        scene_image(story, scene, i - 1, image_path)

        print(f"🗣️ Generating Hindi narration {i}/{SCENE_COUNT}")
        make_tts_sync(scene["narration"], audio_path)

        shutil.copy2(image_path, IMAGES_DIR / image_path.name)
        shutil.copy2(audio_path, AUDIO_DIR / audio_path.name)

def render_remotion():
    if not (REMOTION_DIR / "node_modules").exists():
        print("📦 Installing Remotion dependencies...")
        subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund"],
            cwd=REMOTION_DIR,
            check=True,
        )

    print("🎬 Rendering with Remotion...")
    subprocess.run(
        ["npm", "run", "render"],
        cwd=REMOTION_DIR,
        check=True,
    )

    if not OUT.exists() or OUT.stat().st_size == 0:
        raise RuntimeError("Remotion did not produce toon_kids_short.mp4")

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    print("==========================================")
    print("TOON KIDS — REMOTION PRODUCTION ENGINE")
    print("==========================================")
    print(f"Text model: {TEXT_MODEL}")
    print(f"Scenes: {SCENE_COUNT} x {SCENE_SECONDS}s")
    print("Renderer: Remotion")
    print(f"Run slot: {RUN_SLOT}")

    for p in WORK.glob("*"):
        if p.is_file():
            p.unlink()

    history = load_history()
    story = None

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            for attempt in range(5):
                topic = choose_topic(history)
                candidate = make_story(client, topic, history)
                candidate["topic"] = topic
                if not is_duplicate(candidate, history):
                    story = candidate
                    break
                print(f"⚠️ Duplicate-like story detected; regenerating ({attempt + 1}/5)")
        except Exception as exc:
            print(f"⚠️ Gemini unavailable/exhausted; switching to local story: {exc}")

    if story is None:
        story = local_story(history)
        print("🆓 Local fallback story selected.")

    print(f"📖 Story: {story.get('title')}")
    print(f"💡 Moral: {story.get('moral')}")

    prepare_assets(story)
    render_remotion()

    metadata = {
        "title": story.get("title", ""),
        "topic": story.get("topic", ""),
        "moral": story.get("moral", ""),
        "scene_count": SCENE_COUNT,
        "scene_seconds": SCENE_SECONDS,
        "target_duration_seconds": SCENE_COUNT * SCENE_SECONDS,
        "video_generator": "remotion",
        "art_generator": "local_pillow_cartoon",
        "tts": "edge-tts",
        "text_model": TEXT_MODEL if api_key else "local_fallback",
        "run_slot": RUN_SLOT,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    video_id = upload_youtube(story)
    if video_id:
        metadata["youtube_video_id"] = video_id
        metadata["youtube_url"] = f"https://youtu.be/{video_id}"

    META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    fingerprint = hashlib.sha256(norm(story_text(story)).encode("utf-8")).hexdigest()
    history.append({
        "title": story.get("title", ""),
        "topic": story.get("topic", ""),
        "moral": story.get("moral", ""),
        "story_text": story_text(story),
        "fingerprint": fingerprint,
        "youtube_video_id": video_id,
        "created_at_utc": metadata["created_at_utc"],
    })
    save_history(history)

    print("==========================================")
    print("✅ TOON KIDS REMOTION SHORT COMPLETE")
    print(f"🎥 Output: {OUT}")
    print(f"⏱️ Duration: {SCENE_COUNT * SCENE_SECONDS}s")
    if video_id:
        print(f"📺 YouTube: https://youtu.be/{video_id}")
    print("==========================================")

if __name__ == "__main__":
    main()
