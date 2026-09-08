import os
import json
import time
import asyncio
import hashlib
import secrets
import subprocess
from pathlib import Path
from difflib import SequenceMatcher

from google import genai
from google.genai import types
import edge_tts
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ============================================================
# TOON KIDS — VEO 3.1 STORY ENGINE
# 7 x 8-second portrait scenes = ~56-second YouTube Short
# ============================================================

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_short.mp4"
META = BASE / "story_metadata.json"
HISTORY = BASE / "story_history.json"
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")
FALLBACK_TEXT_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-fast-generate-preview")
TTS_RATE = os.getenv("TTS_RATE", "+8%")
RUN_SLOT = os.getenv("RUN_SLOT", "manual")
UPLOAD_YOUTUBE = os.getenv("UPLOAD_YOUTUBE", "true").lower() == "true"
SCENE_COUNT = 7
SCENE_SECONDS = 8

CHARACTERS = [
    "छोटा खरगोश", "नन्हा हाथी", "प्यारा पिल्ला", "छोटी गिलहरी", "मजेदार बंदर",
    "नन्हा पांडा", "छोटा कछुआ", "प्यारी बिल्ली", "नन्हा हिरन", "छोटा तोता",
    "मजेदार पेंगुइन", "नन्हा भालू", "छोटी लोमड़ी", "प्यारा जिराफ"
]
PLACES = [
    "जादुई जंगल", "रंगीन गाँव", "चमकता बगीचा", "बादलों का शहर", "मजेदार स्कूल",
    "इंद्रधनुषी पहाड़", "सतरंगी नदी", "खिलौनों का शहर", "फूलों की घाटी", "जादुई बाजार"
]
OBJECTS = [
    "चमकती चाबी", "जादुई घंटी", "उड़ने वाली पतंग", "सुनहरी गेंद", "रहस्यमयी नक्शा",
    "जादुई किताब", "चमकता सितारा", "रंग बदलने वाला फूल", "संगीत बॉक्स", "जादुई पेंसिल"
]


def load_history():
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(history):
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def norm(s):
    return " ".join(str(s).lower().split())


def story_text(story):
    parts = [story.get("title", ""), story.get("moral", ""), story.get("topic", "")]
    for scene in story.get("scenes", []):
        parts.extend([scene.get("narration", ""), scene.get("visual", "")])
    return " ".join(parts)


def similar(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def is_duplicate(story, history):
    current = story_text(story)
    title = story.get("title", "")
    fp = hashlib.sha256(norm(current).encode("utf-8")).hexdigest()
    for item in history:
        if isinstance(item, str):
            old_text, old_title = item, ""
        else:
            old_text = item.get("story_text", item.get("topic", ""))
            old_title = item.get("title", "")
            if item.get("fingerprint") == fp:
                return True
        if title and old_title and similar(title, old_title) >= 0.84:
            return True
        if old_text and similar(current, old_text) >= 0.78:
            return True
    return False


def choose_topic(history):
    used = {norm(x if isinstance(x, str) else x.get("topic", "")) for x in history}
    for _ in range(200):
        c = secrets.choice(CHARACTERS)
        p = secrets.choice(PLACES)
        o = secrets.choice(OBJECTS)
        topic = f"{c} का मजेदार रोमांच: {p} में {o} मिलने की कहानी, जिसमें एक छोटी समस्या, मजेदार खोज और प्यारा सरप्राइज हो।"
        if norm(topic) not in used:
            return topic
    return f"एक बिल्कुल नई बच्चों की कहानी {secrets.token_hex(6)}"


def make_story(client, topic, history):
    history_titles = []
    for item in history[-25:]:
        if isinstance(item, dict) and item.get("title"):
            history_titles.append(item["title"])
        elif isinstance(item, str):
            history_titles.append(item[:100])

    prompt = f"""
तुम एक expert Hindi preschool YouTube Shorts storyteller हो।
एक बिल्कुल नई, मजेदार, प्यारी और आसानी से समझ आने वाली कहानी बनाओ।

TOPIC SEED:
{topic}

पुरानी कहानियों/टाइटल से बचो:
{json.dumps(history_titles, ensure_ascii=False)}

STRICT OUTPUT: केवल valid JSON, कोई markdown नहीं।
Schema:
{{
  "title": "छोटा catchy Hindi title",
  "topic": "one-line story topic",
  "moral": "एक बहुत छोटा positive lesson",
  "character": "मुख्य character का पूरा fixed description",
  "scenes": [
    {{"narration":"12-18 सरल Hindi words", "visual":"detailed visual action", "camera":"camera direction"}}
  ]
}}

Rules:
- Exactly {SCENE_COUNT} scenes.
- हर scene लगभग 8 seconds के narration के लिए हो; narration 12-18 सरल Hindi words.
- कहानी scene 1 से शुरू होकर scene 7 में naturally खत्म हो।
- Same main character, same appearance, same outfit पूरे video में।
- हर scene में एक clear visual action हो; static slideshow जैसा नहीं।
- No scary violence, danger, weapons, horror or sad ending.
- Preschool-friendly, colorful, funny, wholesome.
- Scene 7 में moral naturally बोले जाने लायक हो।
- Title 45 characters से छोटा और catchy हो।
"""

    last_error = None
    for model in [TEXT_MODEL, FALLBACK_TEXT_MODEL]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            scenes = data.get("scenes", [])
            if len(scenes) != SCENE_COUNT:
                raise ValueError(f"Expected {SCENE_COUNT} scenes, got {len(scenes)}")
            data["character"] = str(data.get("character", "प्यारा cartoon child-friendly animal"))
            data["moral"] = str(data.get("moral", "मिल-जुलकर मदद करना सबसे अच्छा है।"))
            return data
        except Exception as exc:
            last_error = exc
            print(f"⚠️ Story model {model} failed: {exc}")
            time.sleep(2)
    raise RuntimeError(f"Story generation failed: {last_error}")


def veo_prompt(story, scene, index):
    continuity = story.get("character", "cute child-friendly cartoon animal")
    narration = scene.get("narration", "")
    visual = scene.get("visual", "")
    camera = scene.get("camera", "gentle cinematic camera movement")
    return f"""
Create an 8-second high-quality 3D animated preschool cartoon scene for a vertical 9:16 YouTube Short.

CHARACTER CONTINUITY — MUST NOT CHANGE:
{continuity}

STORY TITLE: {story.get('title','')}
SCENE {index + 1} OF {SCENE_COUNT}

VISUAL ACTION:
{visual}

CAMERA:
{camera}

The character must remain visually identical to the continuity description. Bright cheerful colors, polished family-friendly 3D animation, expressive face, soft cinematic lighting, smooth motion, appealing composition, clear foreground subject, playful environment.

Hindi narration intended for this scene (use as semantic guidance, but DO NOT display any text on screen):
{narration}

IMPORTANT:
- No subtitles, captions, logos, watermarks, signs or written text.
- No visible dialogue text.
- No scary imagery or violence.
- Keep the action simple enough to understand instantly.
- Natural playful ambient sound is okay, but final pipeline may replace the audio with Hindi narration.
"""


def wait_for_operation(client, operation, label):
    started = time.time()
    while not operation.done:
        elapsed = int(time.time() - started)
        print(f"⏳ {label}: waiting for Veo... {elapsed}s")
        time.sleep(10)
        operation = client.operations.get(operation)
        if elapsed > 900:
            raise TimeoutError(f"Veo operation timed out: {label}")
    return operation


def generate_veo_scene(client, prompt, output_path, scene_number):
    print(f"🎬 Generating Veo scene {scene_number}/{SCENE_COUNT}")
    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        config=types.GenerateVideosConfig(
            number_of_videos=1,
            aspect_ratio="9:16",
            duration_seconds=8,
            resolution="1080p",
        ),
    )
    operation = wait_for_operation(client, operation, f"scene {scene_number}")
    generated = operation.response.generated_videos[0]
    client.files.download(file=generated.video, destination=str(output_path))
    if not output_path.exists() or output_path.stat().st_size < 10000:
        raise RuntimeError(f"Veo returned no usable video for scene {scene_number}")
    print(f"✅ Scene {scene_number}: {output_path.stat().st_size / 1024 / 1024:.1f} MB")


async def make_tts(text, output_path):
    communicate = edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate=TTS_RATE)
    await communicate.save(str(output_path))


def make_tts_sync(text, output_path):
    asyncio.run(make_tts(text, output_path))


def ffmpeg_run(args):
    print("🔧", " ".join(str(x) for x in args))
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        print(result.stdout[-6000:])
        raise RuntimeError("FFmpeg command failed")
    return result.stdout


def prepare_scene_video(video_path, tts_path, out_path):
    # Use Veo visual stream and exact Hindi TTS. Veo's generated audio is intentionally replaced
    # so narration timing remains deterministic and does not drift between scenes.
    ffmpeg_run([
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(tts_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-t", str(SCENE_SECONDS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", "30", "-pix_fmt", "yuv420p",
        "-af", "apad=pad_dur=8,atrim=0:8,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(out_path),
    ])


def concat_scenes(scene_paths):
    concat_file = WORK / "concat.txt"
    concat_file.write_text("".join(f"file '{p.resolve()}'\n" for p in scene_paths), encoding="utf-8")
    ffmpeg_run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart", str(OUT),
    ])


def upload_youtube(story):
    if not UPLOAD_YOUTUBE:
        print("ℹ️ YouTube upload disabled")
        return None

    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError("Missing YouTube OAuth secrets")

    credentials = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    youtube = build("youtube", "v3", credentials=credentials)

    title = str(story.get("title", "Toon Kids Story"))[:95]
    if RUN_SLOT == "0":
        title = f"{title} 🐰 | Kids Story #Shorts"
    elif RUN_SLOT == "1":
        title = f"{title} 🌈 | Kids Story #Shorts"
    else:
        title = f"{title} 🎈 | Kids Story #Shorts"

    description = (
        f"{story.get('topic','')}\n\n"
        f"🌟 Moral: {story.get('moral','')}\n\n"
        "प्यारी हिंदी बच्चों की कहानी, fun cartoon adventure और learning के साथ। "
        "ऐसी मजेदार kids stories के लिए subscribe करें!\n\n"
        "#Shorts #Kids #KidsStory #HindiStory #Cartoon #KidsVideo #MoralStory"
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "24",
            "tags": ["kids", "kids story", "hindi story", "cartoon", "moral story", "children story", "youtube shorts"],
            "defaultLanguage": "hi",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": True,
        },
    }

    print("📤 Uploading to YouTube...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(OUT), mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"📤 Upload: {int(status.progress() * 100)}%")
    video_id = response.get("id")
    print(f"✅ YouTube uploaded: https://youtu.be/{video_id}")
    return video_id


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")

    print("==========================================")
    print("TOON KIDS — VEO 3.1")
    print("==========================================")
    print(f"Text model: {TEXT_MODEL}")
    print(f"Veo model: {VEO_MODEL}")
    print(f"Scenes: {SCENE_COUNT} x {SCENE_SECONDS}s")
    print(f"Run slot: {RUN_SLOT}")

    # Clean only generated work; history is permanent.
    for p in WORK.glob("*"):
        if p.is_file():
            p.unlink()

    client = genai.Client(api_key=api_key)
    history = load_history()

    # Generate a fresh story, retrying if it resembles an older one.
    for attempt in range(8):
        topic = choose_topic(history)
        story = make_story(client, topic, history)
        story["topic"] = topic
        if not is_duplicate(story, history):
            break
        print(f"⚠️ Duplicate-like story detected; regenerating ({attempt + 1}/8)")
    else:
        raise RuntimeError("Could not generate a sufficiently unique story")

    print(f"📖 Story: {story.get('title')}")
    print(f"💡 Moral: {story.get('moral')}")

    scene_paths = []
    for i, scene in enumerate(story["scenes"]):
        raw_video = WORK / f"veo_{i+1:02d}.mp4"
        narration_audio = WORK / f"tts_{i+1:02d}.mp3"
        final_scene = WORK / f"scene_{i+1:02d}.mp4"

        prompt = veo_prompt(story, scene, i)
        generate_veo_scene(client, prompt, raw_video, i + 1)

        print(f"🗣️ Generating Hindi narration {i+1}/{SCENE_COUNT}")
        make_tts_sync(scene["narration"], narration_audio)
        prepare_scene_video(raw_video, narration_audio, final_scene)
        scene_paths.append(final_scene)

    concat_scenes(scene_paths)

    metadata = {
        "title": story.get("title", ""),
        "topic": story.get("topic", ""),
        "moral": story.get("moral", ""),
        "scene_count": SCENE_COUNT,
        "scene_seconds": SCENE_SECONDS,
        "target_duration_seconds": SCENE_COUNT * SCENE_SECONDS,
        "veo_model": VEO_MODEL,
        "text_model": TEXT_MODEL,
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
    print("✅ TOON KIDS SHORT COMPLETE")
    print(f"🎥 Output: {OUT}")
    print(f"⏱️ Duration target: {SCENE_COUNT * SCENE_SECONDS}s")
    if video_id:
        print(f"📺 YouTube: https://youtu.be/{video_id}")
    print("==========================================")


if __name__ == "__main__":
    main()
