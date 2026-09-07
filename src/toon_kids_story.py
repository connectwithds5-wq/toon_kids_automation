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
# TOON KIDS V5 — ENGAGING STORY ENGINE
# ============================================================

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_short.mp4"
META = BASE / "story_metadata.json"
HISTORY = BASE / "story_history.json"
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")
FALLBACK_TEXT_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
CLOUDFLARE_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
TTS_RATE = os.getenv("TTS_RATE", "+18%")
TTS_PITCH = os.getenv("TTS_PITCH", "+4Hz")
RUN_SLOT = os.getenv("RUN_SLOT", "manual")
SCENE_COUNT = 10
MAX_DUPLICATE_RETRIES = 8
TARGET_MIN_SECONDS = 48
TARGET_MAX_SECONDS = 60

# ============================================================
# STORY DNA
# ============================================================

CHARACTERS = [
    "खरगोश", "बंदर", "हाथी", "गिलहरी", "पिल्ला", "तोता", "बिल्ली",
    "चूहा", "हिरन", "भालू", "लोमड़ी", "चिड़िया", "रोबोट", "कछुआ",
    "तितली", "पेंगुइन", "बकरी", "ड्रैगन", "मछली", "पांडा", "जिराफ",
    "घोड़ा", "मेंढक", "मधुमक्खी", "उल्लू", "भेड़ का बच्चा", "कंगारू"
]

COLORS = [
    "गोल्डन पीला", "आसमान नीला", "कोरल नारंगी", "पुदीना हरा",
    "लैवेंडर बैंगनी", "चटख लाल", "नीला-हरा", "गुलाबी", "चॉकलेट भूरा"
]

OUTFITS = [
    "पीली हुडी और लाल स्नीकर्स",
    "नीली जैकेट और पीले जूते",
    "हरा छोटा बैकपैक और नारंगी कैप",
    "लाल स्वेटर और नीली छोटी टोपी",
    "बैंगनी ओवरऑल और सफेद जूते",
    "नारंगी जैकेट और हरे स्नीकर्स"
]

PLACES = [
    "जादुई जंगल", "रंगीन गाँव", "चमकता बगीचा", "बादलों का शहर",
    "समुद्र किनारा", "इंद्रधनुषी पहाड़", "रहस्यमयी तालाब", "खिलौनों का शहर",
    "फूलों की घाटी", "सितारों की दुनिया", "मजेदार स्कूल", "जादुई बाजार",
    "बारिश वाला जंगल", "बर्फीली पहाड़ी", "गुब्बारों की दुनिया", "सतरंगी नदी",
    "सूरजमुखी का बगीचा", "चॉकलेट की दुनिया", "जादुई रेलवे स्टेशन",
    "पतंगों का शहर", "संगीत वाला जंगल", "रोबोटों का छोटा शहर"
]

OBJECTS = [
    "चमकती चाबी", "रहस्यमयी डिब्बा", "उड़ने वाली पतंग", "जादुई घंटी",
    "सुनहरी गेंद", "रंग बदलने वाला छाता", "जादुई किताब", "चमकता सितारा",
    "बोलने वाला खिलौना", "सतरंगी पंख", "गायब होने वाली टोपी", "जादुई घड़ी",
    "चमकता सिक्का", "रहस्यमयी नक्शा", "मुस्कुराता पौधा", "जादुई सीटी",
    "चॉकलेट का पेड़", "चमकदार पत्थर", "रंग बदलने वाला फूल", "उड़ने वाली किताब",
    "जादुई जूते", "सतरंगी छड़ी", "संगीत बॉक्स", "गायब होने वाला खिलौना",
    "चमकती सीप", "जादुई पेंसिल"
]

PROBLEMS = [
    "वह चीज़ अचानक गायब हो जाती है",
    "रास्ता तीन मजेदार दिशाओं में बंट जाता है",
    "एक दोस्त को बहुत जल्दी मदद चाहिए",
    "जादुई चीज़ सही रंग पहचान नहीं पा रही",
    "एक आवाज़ बार-बार गलत जगह से आती है",
    "छोटी चीज़ बहुत बड़ी परेशानी बना देती है",
    "सबको लगता है कि राज कुछ और है",
    "अचानक तेज़ बारिश शुरू हो जाती है",
    "पहेली का जवाब उल्टा काम करता है",
    "मदद करने वाला दोस्त खुद फँस जाता है",
    "सही रास्ता केवल हँसने पर दिखाई देता है",
    "जरूरी चीज़ का आखिरी टुकड़ा नहीं मिलता",
    "सरप्राइज गलती से शुरू हो जाता है",
    "सब ठीक लगता है, लेकिन एक चीज़ अजीब है",
    "नायक को डर के बावजूद आगे बढ़ना पड़ता है",
    "मजेदार रेस में नियम बदल जाते हैं",
    "खजाना सामने होते हुए भी दिखाई नहीं देता",
    "दो दोस्त एक ही सुराग को अलग समझते हैं"
]

TWISTS = [
    "वस्तु खुद सही रास्ता दिखाती है",
    "असल सुराग बिल्कुल पास छुपा था",
    "जो डरावना लगा वह बहुत मजेदार निकला",
    "गलती ही सही समाधान बन जाती है",
    "हँसी से जादू चालू हो जाता है",
    "मदद माँगना ही सही जवाब साबित होता है",
    "छोटा सा काम बड़ा सरप्राइज बन जाता है",
    "समस्या समझा गया दोस्त असल में मददगार था",
    "अंत में सबको मिलकर एक नया दोस्त मिलता है",
    "राज खुलते ही पूरा माहौल खुशी से भर जाता है"
]

SFX = ["pop", "whoosh", "sparkle", "boing", "giggle", "none"]

# ============================================================
# HELPERS / HISTORY
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
    # Permanent history. NEVER truncate.
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def story_fingerprint(story, topic):
    raw = " | ".join([
        story.get("title", ""), topic, story.get("moral", ""),
        " ".join(s.get("narration", "") for s in story.get("scenes", []))
    ])
    return hashlib.sha256(norm(raw).encode("utf-8")).hexdigest()


def compact_story_text(story, topic):
    parts = [story.get("title", ""), topic, story.get("moral", "")]
    for scene in story.get("scenes", []):
        parts += [scene.get("narration", ""), scene.get("action", ""), scene.get("visual_event", "")]
    return " ".join(parts)


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    seq = SequenceMatcher(None, norm(a), norm(b)).ratio()
    return max(jaccard, seq * 0.90)


def is_duplicate_story(story, topic, history):
    fp = story_fingerprint(story, topic)
    current = compact_story_text(story, topic)
    title = story.get("title", "")
    for item in history:
        if isinstance(item, str):
            old_fp, old_text, old_title = "", item, ""
        else:
            old_fp = item.get("fingerprint", "")
            old_text = item.get("story_text") or item.get("topic", "")
            old_title = item.get("title", "")
        if old_fp and old_fp == fp:
            return True, "exact fingerprint"
        if title and old_title and similarity(title, old_title) >= 0.82:
            return True, "similar title"
        if old_text and similarity(current, old_text) >= 0.76:
            return True, "high story similarity"
    return False, ""


def choose_topic(history):
    used = {norm(x if isinstance(x, str) else x.get("topic", "")) for x in history}
    for _ in range(300):
        character = secrets.choice(CHARACTERS)
        place = secrets.choice(PLACES)
        obj = secrets.choice(OBJECTS)
        problem = secrets.choice(PROBLEMS)
        twist = secrets.choice(TWISTS)
        topic = f"{character} का रोमांच: {place} में {obj}; समस्या: {problem}; ट्विस्ट: {twist}।"
        if norm(topic) not in used:
            return topic
    return f"एक बिल्कुल नया बच्चों का एडवेंचर {secrets.token_hex(12)}"


def make_locked_character():
    species = secrets.choice(CHARACTERS)
    color = secrets.choice(COLORS)
    outfit = secrets.choice(OUTFITS)
    eye = secrets.choice(["बड़ी चमकीली भूरी आँखें", "बड़ी चमकीली हरी आँखें", "बड़ी चमकीली नीली आँखें"])
    feature = secrets.choice([
        "बायाँ कान थोड़ा मुड़ा हुआ", "गाल पर छोटा दिल जैसा निशान",
        "गले में छोटी घंटी", "नाक पर दो प्यारे छोटे डॉट्स",
        "एक छोटा स्टार बैज"
    ])
    return (
        f"मुख्य नायक: छोटा प्यारा {species}; {color} रंग; गोल मुलायम शरीर; "
        f"{eye}; {outfit}; {feature}; हमेशा यही चेहरा, यही रंग, यही कपड़े, "
        f"यही शरीर और यही पहचान। कोई इंसान मुख्य नायक नहीं है।"
    )

# ============================================================
# GEMINI STORY
# ============================================================

def is_retryable_gemini(exc):
    text = str(exc).upper()
    return any(x in text for x in ["503", "UNAVAILABLE", "HIGH DEMAND", "429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE LIMIT", "INTERNAL"])


def generate_story(topic, history):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    client = genai.Client(api_key=api_key)
    locked = make_locked_character()

    recent = history[-30:]
    avoid = "\n".join(
        (x if isinstance(x, str) else f"{x.get('title','')} — {x.get('topic','')}")
        for x in recent
    )

    prompt = f"""
Create ONE ORIGINAL Hindi kids YouTube Short story.

RANDOM STORY DNA:
{topic}

LOCKED MAIN CHARACTER — MUST NEVER CHANGE:
{locked}

AUDIENCE: children ages 4-10.
LANGUAGE: natural spoken Hindi, simple words, playful, energetic.
TARGET LENGTH: 50-58 seconds. TOTAL narration including moral: 115-130 Hindi words.

IMPORTANT: This must feel like a tiny animated movie, NOT a slideshow.
The story must have a clear goal, escalating problem, funny surprise, physical action,
and a satisfying visual payoff.

EXACTLY {SCENE_COUNT} scenes.

SCENE TIMING:
- Scene 1 hook: 2.5-4 sec, immediately surprising.
- Scenes 2-8: about 4.5-5.5 sec each.
- Scene 9 reveal: 4-5 sec.
- Scene 10 payoff + moral: 4-5 sec.

Every scene MUST contain:
- narration: short spoken Hindi
- text: max 5 Hindi words
- action: one concrete physical action
- emotion: face/body emotion
- camera: dynamic shot direction
- visual_event: a concrete visible event that changes the situation
- image_prompt: first frame prompt
- image_prompt_2: second frame prompt
- sfx: one of {SFX}

STORY PACING:
1. Start IN THE MIDDLE of something surprising. No greetings.
2. Introduce the hero in one sentence.
3. Give the hero a simple goal.
4. Make the problem visibly worse.
5. Add a funny reaction or mistake.
6. Add a fast challenge/chase/discovery.
7. Hero tries a clever solution.
8. Solution almost fails, then a clue appears.
9. BIG VISUAL REVEAL / payoff.
10. Happy ending + one short memorable moral.

ENGAGEMENT RULES:
- Every scene must change the situation.
- Never spend a scene just explaining.
- Use curiosity questions, surprises, funny reactions and physical actions.
- No repetitive searching scenes.
- No generic "he was happy" filler.
- The hero must DO something in every scene.
- The final reveal must pay off an earlier clue.

CHARACTER LOCK RULES:
- ONLY ONE MAIN CHARACTER: the locked character above.
- Do NOT invent boys, girls, humans, or a different hero.
- Supporting animals are allowed only briefly and must NOT replace the hero.
- Every image prompt MUST repeat the locked character description exactly or nearly exactly.
- The hero must be large, recognizable and clearly performing the action.

IMAGE PROMPTS:
Each prompt must describe an ACTION, not a portrait.
Beat 1 establishes the action; Beat 2 shows the action progressing or reacting.
Use strong foreground/midground/background depth.
Use different compositions: extreme close-up, wide, low-angle, overhead,
tracking, orbit, push-in, reveal, top-down, reaction shot.
Do not put written text in images.
Do not show phones, UI, logos, brands, copyrighted characters, horror or violence.
Do not create a human child as the main character.

PREVIOUS STORIES TO AVOID:
{avoid}

Return ONLY valid JSON in this exact shape:
{{
  "title": "...",
  "hook": "...",
  "character_bible": "{locked}",
  "scenes": [
    {{
      "narration": "...",
      "text": "...",
      "action": "...",
      "emotion": "...",
      "camera": "...",
      "visual_event": "...",
      "image_prompt": "...",
      "image_prompt_2": "...",
      "sfx": "..."
    }}
  ],
  "moral": "..."
}}
"""

    last_exc = None
    for model in [TEXT_MODEL, FALLBACK_TEXT_MODEL]:
        if not model:
            continue
        for attempt in range(3):
            try:
                print(f"Gemini model={model}, attempt={attempt+1}/3")
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=1.18,
                        response_mime_type="application/json"
                    )
                )
                story = json.loads(response.text.strip())
                scenes = story.get("scenes", [])
                if len(scenes) != SCENE_COUNT:
                    raise ValueError(f"Story must contain exactly {SCENE_COUNT} scenes.")
                for key in ["title", "hook", "character_bible", "moral"]:
                    if not story.get(key):
                        raise ValueError(f"Story missing {key}")
                required = ["narration", "text", "action", "emotion", "camera", "visual_event", "image_prompt", "image_prompt_2", "sfx"]
                for i, scene in enumerate(scenes, 1):
                    for key in required:
                        if not scene.get(key):
                            raise ValueError(f"Scene {i} missing {key}")
                    if scene["sfx"] not in SFX:
                        scene["sfx"] = "none"
                # Force the locked bible into the accepted story so prompts cannot drift.
                story["character_bible"] = locked
                return story
            except Exception as exc:
                last_exc = exc
                print("Gemini story error:", str(exc))
                time.sleep((8 if is_retryable_gemini(exc) else 5) * (attempt + 1))
    raise RuntimeError(f"Gemini story generation failed: {last_exc}")

# ============================================================
# IMAGE GENERATION
# ============================================================

def generate_image(prompt, filename):
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not account_id or not api_token:
        raise RuntimeError("Cloudflare credentials are missing.")

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    source = str(prompt).strip()
    if len(source) > 1750:
        source = source[:1750]
    full_prompt = f"""
Premium children's 3D animated movie frame, vertical 9:16.

CHARACTER LOCK — THIS IS CRITICAL:
{source}

VISUAL STYLE:
premium 3D family animation, colorful, warm cinematic lighting,
soft rounded shapes, expressive face, polished render, strong depth,
clear foreground/midground/background.

ACTION LOCK:
Show the hero DOING the described physical action.
No standing portrait. No passport-style pose. No generic smiling pose.
The action must be instantly readable to a child.

CONTINUITY:
Same exact hero identity, same species, same color, same face,
same eyes, same outfit, same accessories, same body proportions.
No human main character. Do not replace the hero with another character.

NO text, captions, subtitles, speech bubbles, logos, brands, watermark,
UI, copyrighted characters, horror or violence.
""".strip()
    if len(full_prompt) > 2000:
        full_prompt = full_prompt[:2000]

    for attempt in range(4):
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                json={"prompt": full_prompt, "steps": 4},
                timeout=180
            )
            if response.status_code == 429:
                if attempt == 3:
                    raise RuntimeError("Cloudflare rate limit after retries.")
                time.sleep(15 * (attempt + 1))
                continue
            if response.status_code >= 500:
                if attempt == 3:
                    raise RuntimeError(f"Cloudflare server error {response.status_code}.")
                time.sleep(10 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"Cloudflare HTTP {response.status_code}: {response.text[:1000]}")
            data = response.json()
            if not data.get("success"):
                raise RuntimeError("Cloudflare image error: " + str(data.get("errors", [])))
            image_b64 = data.get("result", {}).get("image")
            if not image_b64:
                raise RuntimeError("Cloudflare returned no image data.")
            if image_b64.startswith("data:image"):
                image_b64 = image_b64.split(",", 1)[1]
            Path(filename).write_bytes(base64.b64decode(image_b64))
            if Path(filename).stat().st_size == 0:
                raise RuntimeError("Generated image is empty.")
            return Path(filename)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == 3:
                raise RuntimeError("Cloudflare connection failed after retries.") from exc
            time.sleep(10 * (attempt + 1))

# ============================================================
# TTS
# ============================================================

async def _save_tts(text, output):
    import edge_tts
    await edge_tts.Communicate(text, "hi-IN-SwaraNeural", rate=TTS_RATE, pitch=TTS_PITCH).save(str(output))


def tts(story):
    voices = []
    for i, scene in enumerate(story["scenes"], 1):
        text = scene["narration"] + (f" {story['moral']}" if i == SCENE_COUNT else "")
        out = WORK / f"voice_{i:02d}.mp3"
        asyncio.run(_save_tts(text, out))
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"Voice not created: {out}")
        voices.append(out)
    print("Voice settings:", TTS_RATE, TTS_PITCH)
    return voices

# ============================================================
# FFMPEG + AUDIO
# ============================================================

def ffprobe_duration(path):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def run_command(command):
    print("Running:", " ".join(str(x) for x in command))
    subprocess.run(command, check=True)


def esc(text):
    return str(text).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%").replace("\n", " ")


def make_tone(path, kind, duration=0.28):
    rate = 44100
    n = max(1, int(rate * duration))
    presets = {
        "pop": (650, 1050), "whoosh": (180, 1050), "sparkle": (900, 1500),
        "boing": (340, 150), "giggle": (720, 1150), "none": (700, 700)
    }
    start, end = presets.get(kind, (700, 700))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            t = i / rate
            p = i / max(1, n - 1)
            freq = start + (end - start) * p
            env = min(1.0, i / (rate * 0.015)) * min(1.0, (n - i) / (rate * 0.07))
            value = (math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(2 * math.pi * freq * 1.7 * t)) * 0.14 * env
            frames.extend(int(value * 32767).to_bytes(2, "little", signed=True))
        wf.writeframes(frames)
    return path


def make_music(path, duration):
    rate = 44100
    notes = [523.25, 659.25, 783.99, 880.0, 783.99, 659.25, 587.33, 698.46]
    beat = 0.24
    total = int(rate * duration)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        frames = bytearray()
        for i in range(total):
            t = i / rate
            idx = int(t / beat) % len(notes)
            local = t % beat
            env = min(1.0, local / 0.025) * min(1.0, (beat - local) / 0.04)
            f = notes[idx]
            sample = (0.038 * math.sin(2 * math.pi * f * t) + 0.014 * math.sin(2 * math.pi * 2 * f * t)) * env
            frames.extend(int(sample * 32767).to_bytes(2, "little", signed=True))
        wf.writeframes(frames)
    return path

# ============================================================
# VIDEO BUILD
# ============================================================

def build_video(story, voice_files):
    images = []
    bible = story["character_bible"]
    for i, scene in enumerate(story["scenes"], 1):
        scene_imgs = []
        for beat in (1, 2):
            path = WORK / f"scene_{i:02d}_{beat}.png"
            key = "image_prompt" if beat == 1 else "image_prompt_2"
            prompt = (
                f"{bible}\n\nACTION: {scene['action']}\n"
                f"EMOTION: {scene['emotion']}\nCAMERA: {scene['camera']}\n"
                f"VISUAL EVENT: {scene['visual_event']}\nBEAT {beat}: {scene[key]}"
            )
            print(f"Generating image {i}/{SCENE_COUNT}, beat {beat}/2")
            generate_image(prompt, path)
            scene_imgs.append(path)
        images.append(scene_imgs)

    raw_durations = [max(3.2, ffprobe_duration(v)) for v in voice_files]
    total_voice = sum(raw_durations)
    print("Raw total duration:", round(total_voice, 2))

    # Keep the natural TTS if <=60 sec. If slightly long, speed audio only enough to fit 58.5 sec.
    target = min(TARGET_MAX_SECONDS, max(TARGET_MIN_SECONDS, total_voice))
    speed = 1.0
    if total_voice > 58.5:
        speed = min(1.15, total_voice / 58.5)
    if speed != 1.0:
        print(f"Voice total {total_voice:.2f}s -> tempo factor {speed:.3f}")

    scene_durations = []
    scene_audio = []
    for i, (voice, raw) in enumerate(zip(voice_files, raw_durations), 1):
        audio = voice
        if speed != 1.0:
            adjusted = WORK / f"voice_adj_{i:02d}.m4a"
            atempo = speed
            filters = []
            while atempo > 2.0:
                filters.append("atempo=2.0"); atempo /= 2.0
            while atempo < 0.5:
                filters.append("atempo=0.5"); atempo /= 0.5
            filters.append(f"atempo={atempo:.5f}")
            run_command(["ffmpeg", "-y", "-i", str(voice), "-filter:a", ",".join(filters), "-c:a", "aac", "-b:a", "128k", str(adjusted)])
            audio = adjusted
        scene_audio.append(audio)
        scene_durations.append(ffprobe_duration(audio))

    clips = []
    audio_parts = []
    for i, (imgs, scene, duration, voice) in enumerate(zip(images, story["scenes"], scene_durations, scene_audio), 1):
        # Two beats; second beat gets slightly more time for the reaction/payoff.
        b1 = duration * 0.44
        b2 = duration - b1
        for beat_idx, (img, bd) in enumerate(zip(imgs, [b1, b2]), 1):
            clip = WORK / f"clip_{i:02d}_{beat_idx}.mp4"
            frames = max(1, int(bd * 30))
            text = esc(scene["text"] if beat_idx == 1 else "")

            # Stronger motion than V4: zoom + lateral travel + vertical drift.
            if beat_idx == 1:
                if i % 4 == 1:
                    motion = "zoompan=z='min(zoom+0.0020,1.16)':x='iw/2-(iw/zoom/2)-on*0.20':y='ih/2-(ih/zoom/2)-on*0.06'"
                elif i % 4 == 2:
                    motion = "zoompan=z='min(zoom+0.0017,1.14)':x='iw/2-(iw/zoom/2)+on*0.20':y='ih/2-(ih/zoom/2)+on*0.05'"
                elif i % 4 == 3:
                    motion = "zoompan=z='max(1.13-on*0.0010,1.0)':x='iw/2-(iw/zoom/2)-on*0.16':y='ih/2-(ih/zoom/2)+on*0.10'"
                else:
                    motion = "zoompan=z='min(zoom+0.0019,1.15)':x='iw/2-(iw/zoom/2)+on*0.14':y='ih/2-(ih/zoom/2)-on*0.10'"
            else:
                if i % 4 == 1:
                    motion = "zoompan=z='min(zoom+0.0022,1.17)':x='iw/2-(iw/zoom/2)+on*0.22':y='ih/2-(ih/zoom/2)+on*0.08'"
                elif i % 4 == 2:
                    motion = "zoompan=z='max(1.15-on*0.0011,1.0)':x='iw/2-(iw/zoom/2)-on*0.18':y='ih/2-(ih/zoom/2)-on*0.07'"
                elif i % 4 == 3:
                    motion = "zoompan=z='min(zoom+0.0020,1.16)':x='iw/2-(iw/zoom/2)+on*0.18':y='ih/2-(ih/zoom/2)'"
                else:
                    motion = "zoompan=z='min(zoom+0.0018,1.14)':x='iw/2-(iw/zoom/2)-on*0.18':y='ih/2-(ih/zoom/2)'"

            draw = ""
            if text:
                draw = ",drawtext=text='" + text + "':fontcolor=white:fontsize=58:fontfile=/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf:x=(w-text_w)/2:y=h-text_h-190:shadowcolor=black@0.92:shadowx=3:shadowy=3"

            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920," + motion + f":d={frames}:s=1080x1920:fps=30" + draw
            run_command(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", str(bd), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(clip)])
            clips.append(clip)

        # SFX at scene start, kept below speech.
        sfx_kind = scene.get("sfx", "none")
        if sfx_kind != "none":
            sfx = make_tone(WORK / f"sfx_{i:02d}.wav", sfx_kind, 0.34 if sfx_kind == "whoosh" else 0.26)
            out = WORK / f"scene_audio_{i:02d}.m4a"
            run_command([
                "ffmpeg", "-y", "-i", str(voice), "-i", str(sfx),
                "-filter_complex", "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[v];[1:a]adelay=80|80,volume=0.32[s];[v][s]amix=inputs=2:duration=first,loudnorm=I=-15:TP=-1.5:LRA=10[a]",
                "-map", "[a]", "-c:a", "aac", "-b:a", "128k", str(out)
            ])
            audio_parts.append(out)
        else:
            audio_parts.append(voice)

    concat = WORK / "concat.txt"
    concat.write_text("\n".join(f"file '{c.as_posix()}'" for c in clips), encoding="utf-8")
    silent = WORK / "silent.mp4"
    run_command(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)])

    audio_concat = WORK / "audio_concat.txt"
    audio_concat.write_text("\n".join(f"file '{a.as_posix()}'" for a in audio_parts), encoding="utf-8")
    narration = WORK / "narration.m4a"
    run_command(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_concat), "-c:a", "aac", "-b:a", "128k", str(narration)])

    final_video_duration = ffprobe_duration(silent)
    music = make_music(WORK / "music.wav", final_video_duration + 2)
    mixed = WORK / "mixed.m4a"
    run_command([
        "ffmpeg", "-y", "-i", str(narration), "-i", str(music),
        "-filter_complex", "[0:a]volume=1.0[voice];[1:a]volume=0.10[music];[voice][music]amix=inputs=2:duration=first,loudnorm=I=-14:TP=-1:LRA=10[a]",
        "-map", "[a]", "-c:a", "aac", "-b:a", "128k", str(mixed)
    ])
    run_command(["ffmpeg", "-y", "-i", str(silent), "-i", str(mixed), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", str(OUT)])

    if not OUT.exists() or OUT.stat().st_size == 0:
        raise RuntimeError("Final video was not created.")
    print("FINAL VIDEO CREATED:", OUT, "duration=", round(ffprobe_duration(OUT), 2))

# ============================================================
# YOUTUBE
# ============================================================

def upload_youtube():
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    for key in ["YOUTUBE_REFRESH_TOKEN", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET"]:
        if not os.environ.get(key):
            raise RuntimeError(f"{key} is missing.")
    credentials = Credentials(
        None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    youtube = build("youtube", "v3", credentials=credentials)
    metadata = json.loads(META.read_text(encoding="utf-8"))
    title = metadata["title"][:95] + " #Shorts"
    description = (
        metadata["hook"] + "\n\n"
        "🌈 Toon Kids पर रोज़ नई हिंदी कहानी!\n"
        "❤️ इस कहानी से आपको क्या सीख मिली?\n\n"
        "#shorts #toonkids #hindistory #kidsstory #moralstory #hindikahani"
    )
    body = {
        "snippet": {
            "title": title, "description": description,
            "tags": ["toon kids", "hindi kids story", "kids story", "hindi kahani", "moral story", "bachon ki kahani", "kids shorts", "bedtime story"],
            "categoryId": "27"
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": True}
    }
    print("Uploading video to YouTube...")
    response = youtube.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(OUT), mimetype="video/mp4", resumable=True)
    ).execute()
    print("YouTube upload successful! Video ID:", response.get("id"))

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("TOON KIDS AUTOMATION V5 STARTED")
    print("=" * 60)
    for key in ["GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]:
        if not os.environ.get(key):
            raise RuntimeError(f"Required secret missing: {key}")

    history = load_history()
    print("Permanent accepted-story history:", len(history))

    story = None
    topic = None
    for attempt in range(MAX_DUPLICATE_RETRIES):
        candidate_topic = choose_topic(history)
        print(f"Novel story attempt {attempt+1}/{MAX_DUPLICATE_RETRIES}")
        candidate = generate_story(candidate_topic, history)
        dup, reason = is_duplicate_story(candidate, candidate_topic, history)
        if dup:
            print("REJECTED duplicate/similar:", reason)
            continue
        story, topic = candidate, candidate_topic
        break
    if story is None:
        raise RuntimeError("Could not obtain a sufficiently novel story after retries. Nothing uploaded.")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": story["title"], "topic": topic,
        "fingerprint": story_fingerprint(story, topic),
        "story_text": compact_story_text(story, topic),
        "character_bible": story["character_bible"], "moral": story["moral"]
    }
    history.append(entry)
    save_history(history)

    META.write_text(json.dumps({
        "title": story["title"], "hook": story["hook"], "moral": story["moral"],
        "topic": topic, "scenes": SCENE_COUNT, "visual_beats_per_scene": 2,
        "target_duration": "50-58 seconds", "version": "V5"
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    voices = tts(story)
    build_video(story, voices)

    if os.getenv("UPLOAD_YOUTUBE", "true").lower() == "true":
        upload_youtube()
    else:
        print("YouTube upload disabled.")

    print("=" * 60)
    print("TOON KIDS AUTOMATION V5 COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
