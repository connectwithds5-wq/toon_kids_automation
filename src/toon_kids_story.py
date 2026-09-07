import os
import re
import json
import time
import asyncio
import subprocess
import base64
import secrets
import hashlib
import math
import wave
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime, timezone

import requests
from google import genai
from google.genai import types


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_short.mp4"
META = BASE / "story_metadata.json"
HISTORY = BASE / "story_history.json"
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)


# ============================================================
# SETTINGS
# ============================================================

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")
FALLBACK_TEXT_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
CLOUDFLARE_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
RUN_SLOT = os.getenv("RUN_SLOT", "manual")

TTS_RATE = os.getenv("TTS_RATE", "+20%")
TTS_PITCH = os.getenv("TTS_PITCH", "+5Hz")

SCENE_COUNT = 10
MAX_DUPLICATE_RETRIES = 8
TARGET_MIN_SECONDS = 48
TARGET_MAX_SECONDS = 60


# ============================================================
# UNLIMITED RANDOM STORY DNA
# ============================================================

CHARACTERS = [
    "नन्हा खरगोश", "शरारती बंदर", "प्यारा हाथी", "चतुर गिलहरी",
    "नन्हा पिल्ला", "रंगीन तोता", "छोटी बिल्ली", "बहादुर चूहा",
    "नन्हा हिरन", "मजेदार भालू", "चंचल लोमड़ी", "छोटी चिड़िया",
    "नन्हा रोबोट", "दयालु कछुआ", "मुस्कुराती तितली", "नन्हा पेंगुइन",
    "जिज्ञासु बकरी", "छोटा ड्रैगन", "नटखट गिलहरी", "नन्ही मछली",
    "प्यारा पांडा", "छोटा जिराफ", "नन्हा घोड़ा", "मजेदार मेंढक",
    "छोटी मधुमक्खी", "नन्हा उल्लू", "चंचल बंदरिया", "प्यारा भेड़ का बच्चा",
    "नन्हा समुद्री घोड़ा", "छोटा कंगारू"
]

PLACES = [
    "जादुई जंगल", "रंगीन गाँव", "चमकता हुआ बगीचा", "बादलों का शहर",
    "समुद्र किनारा", "इंद्रधनुषी पहाड़", "रहस्यमयी तालाब", "खिलौनों का शहर",
    "चाँदनी वाला जंगल", "फूलों की घाटी", "सितारों की दुनिया", "मजेदार स्कूल",
    "जादुई बाजार", "बारिश वाला जंगल", "बर्फीली पहाड़ी", "गुब्बारों की दुनिया",
    "सतरंगी नदी", "छोटा सा खेत", "सूरजमुखी का बगीचा", "चॉकलेट की दुनिया",
    "बादलों के ऊपर का गाँव", "समुद्र के नीचे की दुनिया", "रंग-बिरंगी कैंडी की घाटी",
    "चमकते फूलों का जंगल", "जादुई रेलवे स्टेशन", "पतंगों का शहर",
    "संगीत वाला जंगल", "खिलखिलाते बादलों की घाटी", "रोबोटों का छोटा शहर",
    "चाँद के पास का बगीचा"
]

OBJECTS = [
    "चमकती चाबी", "रहस्यमयी डिब्बा", "उड़ने वाली पतंग", "जादुई घंटी",
    "सुनहरी गेंद", "रंग बदलने वाला छाता", "छोटी जादुई किताब", "चमकता सितारा",
    "बोलने वाला खिलौना", "अनोखी बोतल", "सतरंगी पंख", "गायब होने वाली टोपी",
    "जादुई घड़ी", "चमकता सिक्का", "छोटा खजाना", "उड़ता गुब्बारा",
    "रहस्यमयी नक्शा", "मुस्कुराता हुआ पौधा", "जादुई सीटी", "चॉकलेट का पेड़",
    "चमकदार पत्थर", "रंग बदलने वाला फूल", "बोलने वाला बैग", "उड़ने वाली किताब",
    "जादुई जूते", "सतरंगी छड़ी", "छोटा संगीत बॉक्स", "गायब होने वाला खिलौना",
    "चमकती हुई सीप", "जादुई पेंसिल"
]

PROBLEMS = [
    "वह चीज़ अचानक गायब हो जाती है",
    "रास्ता तीन मजेदार दिशाओं में बंट जाता है",
    "दोस्त की मदद के लिए समय बहुत कम है",
    "जादुई चीज़ सही रंग पहचान नहीं पा रही",
    "एक आवाज़ बार-बार गलत जगह से आती है",
    "छोटी चीज़ बहुत बड़ी परेशानी बना देती है",
    "सबको लगता है कि राज कुछ और है",
    "अचानक मौसम बदल जाता है",
    "एक पहेली का जवाब उल्टा काम करता है",
    "मदद करने वाला दोस्त खुद फँस जाता है",
    "सही रास्ता केवल हँसने पर दिखाई देता है",
    "एक जरूरी चीज़ का आखिरी टुकड़ा नहीं मिलता",
    "एक सरप्राइज गलती से शुरू हो जाता है",
    "सब कुछ ठीक लगता है, लेकिन एक चीज़ अजीब है",
    "नायक को अपने डर के बावजूद आगे बढ़ना पड़ता है",
    "एक मजेदार रेस में नियम बदल जाते हैं",
    "खजाना सामने होते हुए भी दिखाई नहीं देता",
    "दो दोस्त एक ही सुराग को अलग समझते हैं",
    "एक छोटा जानवर अनजाने में बड़ा रहस्य खोल देता है",
    "समाधान उतना मुश्किल नहीं जितना सब सोचते हैं"
]

TWISTS = [
    "वस्तु खुद रास्ता दिखाती है", "असल रहस्य एक प्यारा दोस्त छुपा रहा था",
    "जो डरावना लगा वह मजेदार निकला", "सुराग बिल्कुल पास ही था",
    "गलती ही सही समाधान बन जाती है", "सब मिलकर काम करते हैं तो जादू शुरू होता है",
    "वस्तु का राज केवल हँसी से खुलता है", "नायक को मदद माँगना ही सही जवाब मिलता है",
    "छोटा सा काम बड़ा सरप्राइज बन जाता है", "आखिर में पता चलता है कि कोई खोया ही नहीं था",
    "एक दोस्त पहले से पूरा प्लान बना चुका था", "मoral सीख कहानी के मजेदार पल से निकलती है",
    "जिसे समस्या समझा गया वही असली मददगार था", "अंत में सबको मिलकर एक नया दोस्त मिलता है",
    "राज खुलते ही पूरा माहौल खुशी से भर जाता है"
]

ACTIONS = [
    "एक खोई चीज़ खोजने निकलता है", "अपने दोस्त की मदद करता है",
    "एक मजेदार पहेली हल करता है", "सबको एक साथ इकट्ठा करता है",
    "एक छोटी गलती को ठीक करता है", "एक अनोखी प्रतियोगिता में भाग लेता है",
    "एक रहस्यमयी रास्ते पर जाता है", "बारिश से पहले एक काम पूरा करता है",
    "एक नए दोस्त से मिलता है", "एक छोटी मुसीबत का मजेदार हल निकालता है",
    "एक सरप्राइज पार्टी बचाता है", "एक खोया हुआ खजाना ढूँढता है",
    "एक अजीब आवाज़ का राज पता करता है", "सबको हँसाने वाला खेल शुरू करता है",
    "एक जादुई चीज़ को सही जगह पहुँचाता है", "अपने डर पर काबू पाता है",
    "एक दोस्त के लिए सरप्राइज तैयार करता है", "एक रहस्यमयी दरवाजा खोलता है",
    "एक मजेदार रेस में शामिल होता है", "एक खोई हुई दोस्ती वापस लाता है",
    "एक बड़ी समस्या का छोटा सा हल ढूँढता है", "एक अजीब सपने का मतलब पता करता है",
    "सबके साथ मिलकर एक शानदार काम करता है", "एक अनोखे मेले में पहुँच जाता है",
    "एक रहस्यमयी आवाज़ का पीछा करता है"
]

# ============================================================
# HELPERS + PERMANENT HISTORY
# ============================================================

def norm(value):
    return re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", str(value).lower()).strip()


def tokens(value):
    return {x for x in norm(value).split() if len(x) > 1}


def load_history():
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_history(history):
    # IMPORTANT: no [-1000:] cap. History is intentionally permanent.
    HISTORY.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def story_fingerprint(story, topic):
    scenes = story.get("scenes", [])
    raw = " | ".join([
        story.get("title", ""),
        topic,
        story.get("moral", ""),
        " ".join(s.get("narration", "") for s in scenes)
    ])
    return hashlib.sha256(norm(raw).encode("utf-8")).hexdigest()


def compact_story_text(story, topic):
    parts = [
        story.get("title", ""),
        topic,
        story.get("moral", ""),
        story.get("character_bible", "")
    ]
    for scene in story.get("scenes", []):
        parts.append(scene.get("narration", ""))
        parts.append(scene.get("image_prompt", ""))
    return " ".join(parts)


def similarity(a, b):
    ta = tokens(a)
    tb = tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    seq = SequenceMatcher(None, norm(a), norm(b)).ratio()
    return max(jaccard, seq * 0.90)


def is_duplicate_story(story, topic, history):
    fp = story_fingerprint(story, topic)
    current = compact_story_text(story, topic)

    for item in history:
        if isinstance(item, str):
            old_text = item
            old_fp = ""
        else:
            old_fp = item.get("fingerprint", "")
            old_text = item.get("story_text") or item.get("topic") or item.get("title", "")

        if old_fp and old_fp == fp:
            return True, "exact fingerprint match"

        # Fast title protection.
        title = story.get("title", "")
        old_title = item.get("title", "") if isinstance(item, dict) else ""
        if title and old_title and similarity(title, old_title) >= 0.82:
            return True, f"very similar title: {old_title}"

        # Semantic-ish local protection. No extra API call and no quota cost.
        if old_text and similarity(current, old_text) >= 0.76:
            return True, "high story similarity"

    return False, ""


def choose_topic(history):
    used_topics = {
        norm(item if isinstance(item, str) else item.get("topic", ""))
        for item in history
    }

    for _ in range(250):
        character = secrets.choice(CHARACTERS)
        place = secrets.choice(PLACES)
        obj = secrets.choice(OBJECTS)
        action = secrets.choice(ACTIONS)
        problem = secrets.choice(PROBLEMS)
        twist = secrets.choice(TWISTS)

        topic = (
            f"{character} का नया रोमांच: {place} में {obj}, "
            f"जहाँ वह {action}, लेकिन {problem}; आखिर में {twist}।"
        )

        if norm(topic) not in used_topics:
            return topic

    # This is only a per-video candidate fallback, NOT a story-count limit.
    return (
        f"{secrets.choice(CHARACTERS)} का बिल्कुल नया एडवेंचर "
        f"{secrets.token_hex(10)}"
    )


# ============================================================
# GEMINI
# ============================================================

def is_retryable_gemini(exc):
    text = str(exc).upper()
    return any(x in text for x in [
        "503", "UNAVAILABLE", "HIGH DEMAND", "429",
        "RESOURCE_EXHAUSTED", "QUOTA EXCEEDED",
        "RATE LIMIT", "INTERNAL"
    ])


def generate_story(topic, history):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key)

    previous_hint = ""
    if history:
        # Keep prompt small: recent accepted titles/topics are enough to steer novelty.
        recent = history[-25:]
        rows = []
        for item in recent:
            if isinstance(item, str):
                rows.append(item)
            else:
                rows.append(item.get("title", "") + " — " + item.get("topic", ""))
        previous_hint = "\n".join(rows)

    prompt = f"""
Create ONE ORIGINAL Hindi kids story for Toon Kids YouTube Shorts.

RANDOM STORY DNA:
{topic}

TARGET:
Children ages 4-10.
Natural spoken Hindi. Fun, energetic, simple vocabulary.
Target 48-60 seconds.
TOTAL NARRATION: about 120-135 Hindi words including the moral.
Keep each scene narration extremely short so the finished voice normally stays under 60 seconds.

IMPORTANT NOVELTY RULE:
Never copy or closely imitate an earlier story.
Change the situation, actions, discoveries, jokes and payoff.
Do not make a story that is merely the same plot with a different animal.
Earlier accepted titles/topics for avoidance:
{previous_hint}

EXACTLY {SCENE_COUNT} SCENES.

Every scene MUST contain:
- narration: 1-2 very short spoken Hindi sentences
- text: maximum 6 Hindi words
- action: a visible physical action or discovery
- emotion: clear facial/body emotion
- camera: a specific dynamic camera direction
- image_prompt: detailed visual prompt for the FIRST visual beat
- image_prompt_2: detailed visual prompt for the SECOND visual beat, showing a clear change in action/composition
- visual_change: describe exactly what changes between the two visual beats
- sfx: one of "pop", "whoosh", "sparkle", "boing", "giggle", "none"

VISUAL PACING:
Every scene must visibly change something.
NO static portrait scenes.
Each scene has TWO distinct visual beats. Beat 1 establishes an action; Beat 2 shows the action progressing, reacting, revealing, or resolving.
The second visual beat must NOT be the same pose or composition as the first.
Use running, jumping, opening, chasing, hiding, discovering, reacting,
falling safely, spinning, pointing, laughing, helping, flying, splashing,
or another clear child-friendly action.
Use varied camera: close-up, wide, low-angle, overhead, tracking,
push-in, pull-back, orbit, reveal.
Each scene should feel like a new beat of a real animated short.

STORY BEATS:
1. 1-2 second curiosity hook.
2. Fast character introduction.
3. Problem appears.
4. First surprising clue.
5. Funny reaction.
6. Escalation / chase / challenge.
7. Clever attempt.
8. Almost-solution with twist.
9. Big satisfying reveal.
10. Happy payoff + memorable simple moral.

CHARACTER CONSISTENCY:
Create a concise character_bible specifying species, age/look, body,
face, eyes, fur/skin, clothes, accessories, distinctive feature.
Repeat the important appearance details inside every image_prompt.

IMAGE STYLE:
cute premium 3D animated movie quality, colorful, expressive,
warm cinematic lighting, soft rounded shapes, child-friendly,
original characters only, vertical 9:16 composition.
No copyrighted characters, logos, brands, watermark, written text,
captions, subtitles or speech bubbles inside images.

Return ONLY valid JSON:
{{
  "title": "...",
  "hook": "...",
  "character_bible": "...",
  "scenes": [
    {{
      "narration": "...",
      "text": "...",
      "action": "...",
      "emotion": "...",
      "camera": "...",
      "image_prompt": "...",
      "image_prompt_2": "...",
      "visual_change": "...",
      "sfx": "..."
    }}
  ],
  "moral": "..."
}}
"""

    models = []
    for model in [TEXT_MODEL, FALLBACK_TEXT_MODEL]:
        if model and model not in models:
            models.append(model)

    last_exc = None

    for model in models:
        for attempt in range(3):
            try:
                print(f"Gemini story model={model}, attempt={attempt + 1}/3")
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=1.15,
                        response_mime_type="application/json"
                    )
                )
                story = json.loads(response.text.strip())
                scenes = story.get("scenes", [])

                if len(scenes) != SCENE_COUNT:
                    raise ValueError(
                        f"Story must contain exactly {SCENE_COUNT} scenes."
                    )

                for key in ["title", "hook", "character_bible", "moral"]:
                    if not story.get(key):
                        raise ValueError(f"Story missing: {key}")

                required_scene = [
                    "narration", "text", "action", "emotion",
                    "camera", "image_prompt", "image_prompt_2",
                    "visual_change", "sfx"
                ]
                valid_sfx = {
                    "pop", "whoosh", "sparkle", "boing", "giggle", "none"
                }

                for i, scene in enumerate(scenes, 1):
                    for key in required_scene:
                        if not scene.get(key):
                            raise ValueError(f"Scene {i} missing {key}.")
                    if scene["sfx"] not in valid_sfx:
                        scene["sfx"] = "none"

                return story

            except Exception as exc:
                last_exc = exc
                print("Gemini story error:", str(exc))
                if not is_retryable_gemini(exc):
                    # Validation errors should be retried on the same model.
                    time.sleep(5 * (attempt + 1))
                else:
                    time.sleep(8 * (attempt + 1))

                if attempt == 2:
                    break

    raise RuntimeError(f"Gemini story generation failed: {last_exc}")


# ============================================================
# CLOUDFLARE IMAGE GENERATION
# ============================================================

def generate_image(prompt, filename):
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not account_id:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is missing.")
    if not api_token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is missing.")

    url = (
        "https://api.cloudflare.com/client/v4/"
        f"accounts/{account_id}/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    )

    source_prompt = str(prompt).strip()
    if len(source_prompt) > 1800:
        source_prompt = source_prompt[:1800]

    full_prompt = f"""
Premium children's 3D animated story frame.

Cute high-quality 3D cartoon, colorful family animation,
warm cinematic lighting, soft rounded shapes, friendly expressive face,
bright cheerful environment, premium animated-film render.

Keep the SAME main character design:
same species, face, eye color, fur/skin color, clothes,
accessories and body proportions.

Make the described ACTION obvious and physically readable.
Strong pose and expression. Dynamic composition. Clear foreground,
midground and background. Vertical 9:16. Leave safe space top/bottom.

SCENE:
{source_prompt}

NO copyrighted characters. NO logos. NO watermark.
NO written words. NO captions. NO subtitles. NO speech bubbles. NO UI.
""".strip()

    if len(full_prompt) > 2000:
        full_prompt = full_prompt[:2000]

    payload = {"prompt": full_prompt, "steps": 4}

    for attempt in range(4):
        try:
            print(f"Cloudflare image attempt {attempt + 1}/4...")
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=180
            )

            if response.status_code == 429:
                if attempt == 3:
                    raise RuntimeError(
                        "Cloudflare rate limit after all retries."
                    )
                time.sleep(15 * (attempt + 1))
                continue

            if response.status_code >= 500:
                if attempt == 3:
                    raise RuntimeError(
                        f"Cloudflare server error {response.status_code}."
                    )
                time.sleep(10 * (attempt + 1))
                continue

            if response.status_code >= 400:
                raise RuntimeError(
                    f"Cloudflare image request failed: HTTP {response.status_code}: "
                    f"{response.text[:1000]}"
                )

            try:
                data = response.json()
            except Exception as exc:
                raise RuntimeError("Invalid Cloudflare API response.") from exc

            if not data.get("success"):
                raise RuntimeError(
                    "Cloudflare image generation failed: "
                    + str(data.get("errors", []))
                )

            image_b64 = data.get("result", {}).get("image")
            if not image_b64:
                raise RuntimeError("Cloudflare returned no image data.")

            if image_b64.startswith("data:image"):
                image_b64 = image_b64.split(",", 1)[1]

            image_bytes = base64.b64decode(image_b64)
            output_path = Path(filename)
            output_path.write_bytes(image_bytes)

            if output_path.stat().st_size == 0:
                raise RuntimeError("Generated image file is empty.")

            print("Image saved:", output_path)
            return output_path

        except requests.Timeout as exc:
            if attempt == 3:
                raise RuntimeError(
                    "Cloudflare request timed out after all retries."
                ) from exc
            time.sleep(10 * (attempt + 1))

        except requests.ConnectionError as exc:
            if attempt == 3:
                raise RuntimeError(
                    "Cloudflare connection failed."
                ) from exc
            time.sleep(10 * (attempt + 1))


# ============================================================
# HINDI TTS — ONE FILE PER SCENE
# ============================================================

async def _save_tts(text, output):
    import edge_tts
    communicate = edge_tts.Communicate(
        text,
        "hi-IN-SwaraNeural",
        rate=TTS_RATE,
        pitch=TTS_PITCH
    )
    await communicate.save(str(output))


def tts(story):
    voice_files = []

    for index, scene in enumerate(story["scenes"], 1):
        text = scene["narration"]
        if index == len(story["scenes"]):
            text = f"{text} {story['moral']}"

        output = WORK / f"voice_{index:02d}.mp3"
        print(f"Generating Hindi voice {index}/{SCENE_COUNT}...")
        asyncio.run(_save_tts(text, output))

        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError(f"Voice file was not created: {output}")

        voice_files.append(output)

    print(
        "Voice settings:",
        f"rate={TTS_RATE}, pitch={TTS_PITCH}"
    )
    return voice_files


# ============================================================
# AUDIO / FFMPEG
# ============================================================

def ffprobe_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return float(result.stdout.strip())


def run_command(command):
    print("Running:", " ".join(str(x) for x in command))
    subprocess.run(command, check=True)


def esc(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("\n", " ")
    )


def make_tone(path, kind, duration=0.32):
    """Generate tiny original synthetic SFX without downloading assets."""
    rate = 44100
    n = max(1, int(rate * duration))
    presets = {
        "pop": (620, 980),
        "whoosh": (260, 900),
        "sparkle": (880, 1320),
        "boing": (320, 180),
        "giggle": (700, 1100),
    }
    start, end = presets.get(kind, (700, 700))

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)

        frames = bytearray()
        for i in range(n):
            t = i / rate
            progress = i / max(1, n - 1)
            freq = start + (end - start) * progress
            env = min(1.0, i / (rate * 0.02))
            env *= min(1.0, (n - i) / (rate * 0.08))
            value = (
                math.sin(2 * math.pi * freq * t)
                + 0.35 * math.sin(2 * math.pi * freq * 1.7 * t)
            ) * 0.16 * env
            frames.extend(int(value * 32767).to_bytes(
                2, "little", signed=True
            ))
        wf.writeframes(frames)

    return path


def make_music(path, duration=70.0):
    """Simple playful original melody; intentionally no external music asset."""
    rate = 44100
    notes = [523.25, 659.25, 783.99, 659.25, 587.33, 698.46, 880.00, 698.46]
    beat = 0.32
    total = int(rate * duration)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)

        frames = bytearray()
        for i in range(total):
            t = i / rate
            idx = int(t / beat) % len(notes)
            local = t % beat
            freq = notes[idx]

            # Soft two-layer melody with gentle pulse.
            env = 0.5 + 0.5 * math.sin(2 * math.pi * local / beat)
            sample = (
                0.055 * math.sin(2 * math.pi * freq * t)
                + 0.022 * math.sin(2 * math.pi * freq * 2 * t)
            ) * env

            frames.extend(int(sample * 32767).to_bytes(
                2, "little", signed=True
            ))

        wf.writeframes(frames)

    return path


# ============================================================
# BUILD VIDEO — 10 ACTION-DRIVEN SCENES
# ============================================================

def build_video(story, voice_files):
    """Build a fast 10-scene short with TWO visual beats per scene."""
    images = []
    bible = str(story["character_bible"])
    if len(bible) > 780:
        bible = bible[:780]

    # --------------------------------------------------------
    # Generate 20 visual keyframes: 2 genuinely different beats
    # for every one of the 10 story scenes.
    # --------------------------------------------------------
    for index, scene in enumerate(story["scenes"], 1):
        scene_images = []
        for beat in (1, 2):
            image_path = WORK / f"scene_{index:02d}_{beat}.png"
            prompt_key = "image_prompt" if beat == 1 else "image_prompt_2"
            image_prompt = (
                "CHARACTER BIBLE:\n" + bible +
                "\n\nACTION:\n" + str(scene.get("action", "")) +
                "\n\nEMOTION:\n" + str(scene.get("emotion", "")) +
                "\n\nCAMERA:\n" + str(scene.get("camera", "")) +
                "\n\nVISUAL CHANGE:\n" + str(scene.get("visual_change", "")) +
                f"\n\nBEAT {beat}:\n" + str(scene.get(prompt_key, scene.get("image_prompt", "")))
            )
            print("=" * 60)
            print(f"Generating image {index}/{SCENE_COUNT}, beat {beat}/2...")
            generate_image(image_prompt, image_path)
            scene_images.append(image_path)
        images.append(scene_images)

    # Actual voice duration drives every visual beat.
    scene_durations = [max(3.8, ffprobe_duration(v)) for v in voice_files]
    total_duration = sum(scene_durations)
    print("Scene voice durations:", [round(x, 2) for x in scene_durations])
    print("Total duration:", round(total_duration, 2), "seconds")

    if total_duration > TARGET_MAX_SECONDS:
        print(
            f"WARNING: voice duration {total_duration:.2f}s exceeds "
            f"target {TARGET_MAX_SECONDS}s. Keeping audio/visual sync."
        )

    clips = []
    scene_audio = []

    for index, (scene_images, scene, duration, voice) in enumerate(
        zip(images, story["scenes"], scene_durations, voice_files), 1
    ):
        # Two quick visual beats within each spoken scene.
        beat1 = max(1.55, duration * 0.48)
        beat2 = max(1.55, duration - beat1)
        beat_durations = [beat1, beat2]

        for beat_index, (image, beat_duration) in enumerate(
            zip(scene_images, beat_durations), 1
        ):
            clip = WORK / f"clip_{index:02d}_{beat_index}.mp4"
            text = esc(scene["text"] if beat_index == 1 else "")
            frames = max(1, int(beat_duration * 30))

            # Deliberately varied camera motion. The second beat reverses
            # direction so the viewer gets a visible change even though
            # the source is a still frame.
            if beat_index == 1:
                if index % 3 == 1:
                    zoom = (
                        "zoompan=z='min(zoom+0.0018,1.14)':"
                        "x='iw/2-(iw/zoom/2)':"
                        "y='ih/2-(ih/zoom/2)'")
                elif index % 3 == 2:
                    zoom = (
                        "zoompan=z='min(zoom+0.0015,1.12)':"
                        "x='iw/2-(iw/zoom/2)-on*0.16':"
                        "y='ih/2-(ih/zoom/2)'")
                else:
                    zoom = (
                        "zoompan=z='max(1.12-on*0.0010,1.0)':"
                        "x='iw/2-(iw/zoom/2)+on*0.14':"
                        "y='ih/2-(ih/zoom/2)'")
            else:
                if index % 3 == 1:
                    zoom = (
                        "zoompan=z='max(1.13-on*0.0009,1.0)':"
                        "x='iw/2-(iw/zoom/2)+on*0.18':"
                        "y='ih/2-(ih/zoom/2)'")
                elif index % 3 == 2:
                    zoom = (
                        "zoompan=z='min(zoom+0.0017,1.14)':"
                        "x='iw/2-(iw/zoom/2)':"
                        "y='ih/2-(ih/zoom/2)-on*0.13'")
                else:
                    zoom = (
                        "zoompan=z='min(zoom+0.0014,1.12)':"
                        "x='iw/2-(iw/zoom/2)-on*0.16':"
                        "y='ih/2-(ih/zoom/2)'")

            drawtext = ""
            if text:
                drawtext = (
                    ",drawtext=text='" + text + "':"
                    "fontcolor=white:fontsize=58:"
                    "fontfile=/usr/share/fonts/truetype/noto/"
                    "NotoSansDevanagari-Regular.ttf:"
                    "x=(w-text_w)/2:y=h-text_h-190:"
                    "shadowcolor=black@0.90:shadowx=3:shadowy=3"
                )

            vf = (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920," + zoom +
                f":d={frames}:s=1080x1920:fps=30" + drawtext
            )

            print(
                f"Building visual beat {index}/{SCENE_COUNT} "
                f"beat {beat_index}/2..."
            )
            run_command([
                "ffmpeg", "-y", "-loop", "1",
                "-i", str(image),
                "-t", str(beat_duration),
                "-vf", vf,
                "-an", "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                str(clip)
            ])
            clips.append(clip)

        # Audio remains exactly one scene long, preserving narration sync.
        sfx_name = scene.get("sfx", "none")
        audio_out = WORK / f"scene_audio_{index:02d}.m4a"

        if sfx_name != "none":
            sfx = make_tone(
                WORK / f"sfx_{index:02d}.wav",
                sfx_name,
                0.28 if sfx_name != "whoosh" else 0.42
            )
            run_command([
                "ffmpeg", "-y",
                "-i", str(voice),
                "-i", str(sfx),
                "-filter_complex",
                "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[v];"
                "[1:a]adelay=120|120,volume=0.48[s];"
                "[v][s]amix=inputs=2:duration=first,"
                "loudnorm=I=-15:TP=-1.5:LRA=10[a]",
                "-map", "[a]",
                "-c:a", "aac", "-b:a", "128k",
                str(audio_out)
            ])
        else:
            run_command([
                "ffmpeg", "-y", "-i", str(voice),
                "-filter:a", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a", "aac", "-b:a", "128k",
                str(audio_out)
            ])

        scene_audio.append(audio_out)

    # Concatenate all 20 visual beats.
    concat_file = WORK / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{c.as_posix()}'" for c in clips),
        encoding="utf-8"
    )
    silent_video = WORK / "silent.mp4"
    run_command([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file), "-c", "copy", str(silent_video)
    ])

    # Concatenate scene audio.
    audio_concat = WORK / "audio_concat.txt"
    audio_concat.write_text(
        "\n".join(f"file '{a.as_posix()}'" for a in scene_audio),
        encoding="utf-8"
    )
    narration_audio = WORK / "narration_mix.m4a"
    run_command([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(audio_concat), "-c:a", "aac", "-b:a", "128k",
        str(narration_audio)
    ])

    # Keep the music clearly underneath narration.
    music = make_music(
        WORK / "music.wav",
        max(65.0, total_duration + 4)
    )
    mixed_audio = WORK / "mixed.m4a"
    run_command([
        "ffmpeg", "-y",
        "-i", str(narration_audio),
        "-i", str(music),
        "-filter_complex",
        "[0:a]volume=1.0[voice];"
        "[1:a]volume=0.16[music];"
        "[voice][music]amix=inputs=2:duration=first,"
        "loudnorm=I=-14:TP=-1:LRA=10[a]",
        "-map", "[a]", "-c:a", "aac", "-b:a", "128k",
        str(mixed_audio)
    ])

    run_command([
        "ffmpeg", "-y",
        "-i", str(silent_video),
        "-i", str(mixed_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", str(OUT)
    ])

    if not OUT.exists() or OUT.stat().st_size == 0:
        raise RuntimeError("Final video was not created.")

    print("FINAL VIDEO CREATED:", OUT)


# ============================================================
# YOUTUBE UPLOAD
# ============================================================

def upload_youtube():
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    required = [
        "YOUTUBE_REFRESH_TOKEN",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET"
    ]
    for key in required:
        if not os.environ.get(key):
            raise RuntimeError(f"{key} is missing.")

    credentials = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    youtube = build("youtube", "v3", credentials=credentials)

    metadata = json.loads(META.read_text(encoding="utf-8"))
    title = metadata["title"][:95] + " #Shorts"

    description = (
        metadata["hook"]
        + "\n\n"
        "🌈 Toon Kids पर रोज़ नई हिंदी कहानी!"
        "\n❤️ इस कहानी से आपको क्या सीख मिली?"
        "\n\n"
        "#shorts #toonkids #hindistory "
        "#kidsstory #moralstory #hindikahani"
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [
                "toon kids", "hindi kids story", "kids story",
                "hindi kahani", "moral story", "bachon ki kahani",
                "kids shorts", "bedtime story"
            ],
            "categoryId": "27"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": True
        }
    }

    print("Uploading video to YouTube...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(
            str(OUT),
            mimetype="video/mp4",
            resumable=True
        )
    )
    response = request.execute()

    print("YouTube upload successful!")
    print("Video ID:", response.get("id"))


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("TOON KIDS AUTOMATION V4 STARTED")
    print("=" * 60)

    required_env = [
        "GEMINI_API_KEY",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID"
    ]
    for key in required_env:
        if not os.environ.get(key):
            raise RuntimeError(f"Required secret missing: {key}")

    history = load_history()
    print("Permanent accepted-story history:", len(history))

    # No total story limit. Each run keeps generating until it gets
    # a novel accepted story, with a finite retry guard for API safety.
    accepted_story = None
    accepted_topic = None

    for generation_attempt in range(MAX_DUPLICATE_RETRIES):
        topic = choose_topic(history)
        print(
            f"Novel story attempt {generation_attempt + 1}/"
            f"{MAX_DUPLICATE_RETRIES}"
        )
        print("Selected topic:", topic)

        story = generate_story(topic, history)
        duplicate, reason = is_duplicate_story(story, topic, history)

        if duplicate:
            print("DUPLICATE/SIMILAR STORY REJECTED:", reason)
            continue

        accepted_story = story
        accepted_topic = topic
        break

    if accepted_story is None:
        raise RuntimeError(
            "Could not obtain a sufficiently novel story after retries. "
            "No story was added to history and no video was uploaded."
        )

    story = accepted_story
    topic = accepted_topic

    print("Accepted NEW story:", story["title"])

    # Save only AFTER duplicate validation.
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": story["title"],
        "topic": topic,
        "fingerprint": story_fingerprint(story, topic),
        "story_text": compact_story_text(story, topic),
        "character_bible": story["character_bible"],
        "moral": story["moral"]
    }
    history.append(entry)
    save_history(history)
    print("Permanent story history saved. Total:", len(history))

    META.write_text(
        json.dumps({
            "title": story["title"],
            "hook": story["hook"],
            "moral": story["moral"],
            "topic": topic,
            "scenes": SCENE_COUNT,
            "visual_beats_per_scene": 2,
            "target_duration": "48-60 seconds"
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("Generating energetic Hindi scene voices...")
    voice_files = tts(story)

    print("Building action-driven video...")
    build_video(story, voice_files)

    upload_enabled = (
        os.getenv("UPLOAD_YOUTUBE", "true").lower() == "true"
    )

    if upload_enabled:
        upload_youtube()
    else:
        print("YouTube upload disabled.")

    print("=" * 60)
    print("TOON KIDS AUTOMATION V4 COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()

