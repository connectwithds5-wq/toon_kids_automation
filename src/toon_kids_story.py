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
# TOON KIDS V6 — CHARACTER-CONTINUITY STORY ENGINE
# ============================================================

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_short.mp4"
META = BASE / "story_metadata.json"
HISTORY = BASE / "story_history.json"
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")
FALLBACK_TEXT_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
CLOUDFLARE_IMAGE_MODEL = os.getenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-4b")
TTS_RATE = os.getenv("TTS_RATE", "+16%")
TTS_PITCH = os.getenv("TTS_PITCH", "+3Hz")
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

    recent = history[-40:]
    avoid = "\n".join(
        (x if isinstance(x, str) else f"{x.get('title','')} — {x.get('topic','')}")
        for x in recent
    )

    prompt = f"""
Create ONE ORIGINAL Hindi kids YouTube Short story that feels like a tiny animated movie.

RANDOM STORY DNA:
{topic}

LOCKED MAIN CHARACTER — NEVER CHANGE:
{locked}

AUDIENCE: children ages 4-10.
LANGUAGE: natural spoken Hindi, very simple words, energetic and funny.
TARGET: 50-58 seconds, 110-125 Hindi words including the moral.
EXACTLY 10 SCENES.

CORE RULE — STORY/IMAGE MATCH:
The image for every scene MUST directly show what that scene's narration says.
Do not write vague image prompts. Each image prompt must name the exact main character,
exact object, exact location, exact physical action, and the visible result of that action.
If narration says "picked up the golden key", the image must visibly show the hero holding
the golden key. If narration says "door opened", the image must visibly show the door opening.

STORY ARC:
1. 0-3 sec: immediate visual hook already in progress; no greeting.
2. Introduce hero + goal.
3. First obstacle.
4. Obstacle gets worse.
5. Funny mistake/reaction.
6. New clue or chase.
7. Clever attempt.
8. Almost fails; important clue appears.
9. Big reveal that pays off the clue.
10. Happy payoff + very short moral.

EVERY SCENE MUST:
- move the story forward
- contain one concrete physical action by the SAME hero
- contain one concrete visual event
- show a clear emotion/reaction
- use a distinct camera composition
- carry forward the same object/location state from the previous scene

CHARACTER LOCK:
- ONLY ONE MAIN CHARACTER: the locked character above.
- NO humans, boys, girls, human children, human heroes, or replacement protagonists.
- Supporting animals may appear only when the story requires them, but they must never replace the hero.
- Every image_prompt MUST start with the locked character description or a near-verbatim version.
- The hero's species, color, eyes, clothes, accessory, face and body proportions MUST stay identical.

VISUAL CONTINUITY:
Scene 1 establishes the world and the important object.
Scenes 2-8 must preserve the same world and object design unless the narration explicitly changes it.
Scene 9 must show the exact payoff/reveal.
Scene 10 must show the hero celebrating the result of the same story.

IMAGE PROMPT RULES:
- 3D animated children's movie, colorful, cinematic, expressive.
- ACTION, not portrait.
- Clearly visible interaction between hero and story object/environment.
- Use varied compositions: wide, close-up, low-angle, overhead, tracking, reveal, reaction.
- No written words, letters, signs, captions, logos, brands, UI, watermark.
- No horror, violence, weapons, politics or adult themes.
- NEVER depict a human as the main character.

Each scene fields:
- narration: 1 short spoken sentence, sometimes 2 very short sentences
- text: maximum 5 Hindi words
- action: exact physical action
- emotion: exact face/body reaction
- camera: shot/composition
- visual_event: what visibly changes
- continuity: what must remain from previous scene
- image_prompt: ONE detailed first/only frame prompt that directly matches narration
- sfx: one of {SFX}

PREVIOUS STORIES TO AVOID:
{avoid}

Return ONLY valid JSON:
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
      "continuity": "...",
      "image_prompt": "...",
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
                        temperature=1.05,
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
                required = ["narration", "text", "action", "emotion", "camera", "visual_event", "continuity", "image_prompt", "sfx"]
                for i, scene in enumerate(scenes, 1):
                    for key in required:
                        if not scene.get(key):
                            raise ValueError(f"Scene {i} missing {key}")
                    if scene["sfx"] not in SFX:
                        scene["sfx"] = "none"
                    # Basic semantic guard: every prompt must contain the locked species.
                    species = locked.split("मुख्य नायक: छोटा प्यारा ",1)[-1].split(";",1)[0]
                    if species not in scene["image_prompt"]:
                        scene["image_prompt"] = f"{locked} {scene['image_prompt']}"
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

def _small_reference(path):
    """Return a <=512px PNG reference for FLUX.2 multi-reference input."""
    from PIL import Image
    src = Path(path)
    out = WORK / f"ref_{src.stem}.png"
    img = Image.open(src).convert("RGB")
    img.thumbnail((512, 512), Image.Resampling.LANCZOS)
    img.save(out, format="PNG", optimize=True)
    return out


def generate_image(prompt, filename, reference_paths=None, width=1024, height=1792):
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not account_id or not api_token:
        raise RuntimeError("Cloudflare credentials are missing.")

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    source = str(prompt).strip()
    if len(source) > 1800:
        source = source[:1800]

    full_prompt = f"""
Premium 3D animated children's movie frame, vertical 9:16.

REFERENCE CONTINUITY:
If a reference image is supplied, preserve the exact identity of the main character from it:
same species, face, eye color, body proportions, fur/skin color, clothing and accessories.
Do NOT replace the character with a human or a different character.

STORY VISUAL:
{source}

The main character MUST be visibly performing the stated action and visibly interacting
with the stated object/environment. The scene must look like a real moment from one continuous
animated story, not a character portrait or a random poster.

STYLE: polished family-friendly 3D animation, colorful, warm cinematic light,
strong depth, expressive face, clear foreground/midground/background, child-friendly.

ABSOLUTELY NO written words, letters, captions, subtitles, speech bubbles, logos,
watermarks, UI, brand marks, human protagonist, horror or violence.
""".strip()

    refs = [_small_reference(x) for x in (reference_paths or [])][:2]

    for attempt in range(4):
        handles = []
        try:
            # FLUX.2 on Cloudflare requires multipart/form-data and supports reference images.
            files = []
            # Use an empty multipart field for text-only generation.
            if refs:
                for idx, ref in enumerate(refs):
                    h = open(ref, "rb")
                    handles.append(h)
                    files.append((f"input_image_{idx}", (ref.name, h, "image/png")))
            data = [
                ("prompt", full_prompt),
                ("width", str(width)),
                ("height", str(height)),
                ("guidance", "4")
            ]
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_token}"},
                data=data,
                files=files if files else {"_multipart": (None, "1")},
                timeout=240
            )
            if response.status_code == 429:
                if attempt == 3:
                    raise RuntimeError("Cloudflare rate limit after retries.")
                time.sleep(15 * (attempt + 1))
                continue
            if response.status_code >= 500:
                if attempt == 3:
                    raise RuntimeError(f"Cloudflare server error {response.status_code}: {response.text[:1000]}")
                time.sleep(10 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"Cloudflare HTTP {response.status_code}: {response.text[:2000]}")
            data_json = response.json()
            if not data_json.get("success"):
                raise RuntimeError("Cloudflare image error: " + str(data_json.get("errors", [])))
            image_b64 = data_json.get("result", {}).get("image")
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
        finally:
            for h in handles:
                try:
                    h.close()
                except Exception:
                    pass


def generate_character_reference(story):
    path = WORK / "character_reference.png"
    prompt = f"""
CHARACTER DESIGN REFERENCE ONLY.
{story['character_bible']}

Create one full-body, front three-quarter view of this EXACT single cute animal character,
centered, fully visible from ears to feet, neutral friendly expression, arms and legs visible.
Clean simple studio background, no other characters, no objects, no text.
This image will be used as a visual identity reference for every scene, so prioritize exact
face, colors, clothes, body proportions and distinctive feature over scenery.
"""
    generate_image(prompt, path, reference_paths=None, width=768, height=768)
    return path

# ============================================================
# TTS
# ============================================================

async def _save_tts(text, output):
    c
    for i, (img, scene, duration, voice) in enumerate(zip(images, story["scenes"], scene_durations, scene_audio), 1):
        clip = WORK / f"clip_{i:02d}.mp4"
        frames = max(1, int(duration * 30))
        text = esc(scene["text"])

        # One strong continuous camera move per scene. The image itself is story-connected;
        # the motion adds life without inventing a second unrelated frame.
        motions = [
            "zoompan=z='min(zoom+0.0018,1.13)':x='iw/2-(iw/zoom/2)-on*0.10':y='ih/2-(ih/zoom/2)'",
            "zoompan=z='min(zoom+0.0016,1.12)':x='iw/2-(iw/zoom/2)+on*0.10':y='ih/2-(ih/zoom/2)-on*0.05'",
            "zoompan=z='max(1.12-on*0.0009,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)+on*0.08'",
            "zoompan=z='min(zoom+0.0019,1.14)':x='iw/2-(iw/zoom/2)+on*0.08':y='ih/2-(ih/zoom/2)'"]
        motion = motions[(i-1) % len(motions)]
        draw = (
            ",drawtext=text='" + text + "':fontcolor=white:fontsize=56:"
            "fontfile=/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf:"
            "x=(w-text_w)/2:y=h-text_h-190:shadowcolor=black@0.92:shadowx=3:shadowy=3"
            if text else ""
        )
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920," + motion + f":d={frames}:s=1080x1920:fps=30" + draw
        print(f"Building connected clip {i}/{SCENE_COUNT}...")
        run_command(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", str(duration), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(clip)])
        clips.append(clip)

        sfx_kind = scene.get("sfx", "none")
        if sfx_kind != "none":
            sfx = make_tone(WORK / f"sfx_{i:02d}.wav", sfx_kind, 0.30 if sfx_kind == "whoosh" else 0.22)
            out = WORK / f"scene_audio_{i:02d}.m4a"
            run_command([
                "ffmpeg", "-y", "-i", str(voice), "-i", str(sfx),
                "-filter_complex", "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[v];[1:a]adelay=70|70,volume=0.24[s];[v][s]amix=inputs=2:duration=first,loudnorm=I=-15:TP=-1.5:LRA=10[a]",
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
    music = make_music(WORK / "music.wav", final_video_duration + 1)
    mixed = WORK / "mixed.m4a"
    run_command([
        "ffmpeg", "-y", "-i", str(narration), "-i", str(music),
        "-filter_complex", "[0:a]volume=1.0[voice];[1:a]volume=0.075[music];[voice][music]amix=inputs=2:duration=first,loudnorm=I=-14:TP=-1:LRA=10[a]",
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
    print("TOON KIDS AUTOMATION V6 STARTED")
    print("=" * 60)
    for key in ["GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]:
        if not os.environ.get(key):
            raise RuntimeError(f"Required secret missing: {key}")

    history = load_history()
    print("Permanent accepted-story history:", len(history))
    print("Cloudflare image model:", CLOUDFLARE_IMAGE_MODEL)

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
        "topic": topic, "scenes": SCENE_COUNT, "visual_beats_per_scene": 1,
        "reference_image_continuity": True,
        "target_duration": "50-58 seconds", "version": "V6"
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    voices = tts(story)
    build_video(story, voices)

    if os.getenv("UPLOAD_YOUTUBE", "true").lower() == "true":
        upload_youtube()
    else:
        print("YouTube upload disabled.")

    print("=" * 60)
    print("TOON KIDS AUTOMATION V6 COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
