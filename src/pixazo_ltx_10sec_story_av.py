import asyncio
import json
import os
import time
from pathlib import Path

import requests
import edge_tts
from google import genai
from google.genai import types

from toon_kids_story import WORK, load_history
from hf_wan_10sec_story_av_v2 import assemble, mux, make_music, make_sfx, fit_voice, sfx_kind

PIXAZO_KEY = os.getenv("PIXAZO_API_KEY", "").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
CATEGORY = os.getenv("CONTENT_CATEGORY", "numbers").strip().lower()
OUT = Path(os.getenv("PIXAZO_OUTPUT", "toon_pixazo_ltx_10sec_learning.mp4"))
META = Path(os.getenv("PIXAZO_METADATA", "pixazo_learning_metadata.json"))
SLOTS = [3.25, 3.35, 3.40]
API_BASE = "https://gateway.pixazo.ai"

CATEGORY_DATA = {
    "numbers": {
        "title": "1 से 10 गिनती",
        "items": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
        "objects": "colorful apples",
        "lesson": "बच्चों को 1 से 10 तक गिनना सिखाना"
    },
    "fruits": {
        "title": "मजेदार फलों की पहचान",
        "items": ["सेब", "केला", "आम", "संतरा", "स्ट्रॉबेरी", "अंगूर", "तरबूज", "अनानास", "नाशपाती", "पपीता"],
        "objects": "bright colorful fruits",
        "lesson": "बच्चों को फलों के नाम पहचानना सिखाना"
    },
    "vegetables": {
        "title": "रंगीन सब्जियाँ",
        "items": ["गाजर", "टमाटर", "आलू", "मटर", "भिंडी", "बैंगन", "मक्का", "फूलगोभी", "पालक", "कद्दू"],
        "objects": "bright colorful vegetables",
        "lesson": "बच्चों को सब्जियों के नाम पहचानना सिखाना"
    },
}

if CATEGORY not in CATEGORY_DATA:
    CATEGORY = "numbers"
DATA = CATEGORY_DATA[CATEGORY]

CINEMATIC_BIBLE = """
Premium polished 3D animated-feature-quality preschool cartoon.
Cute expressive main character, rich colorful environment, soft physically believable lighting,
cinematic depth of field, clean composition, smooth natural motion, polished materials.
Use purposeful cinematic camera language: establishing wides, overhead reveals, tracking/dolly,
low-angle hero shots and gentle push-ins only when useful. Never make every shot a face close-up.
Keep the SAME main character identity, face, body proportions, colors and outfit throughout.
Keep objects visually simple, large and readable. Vertical 9:16 composition with safe margins.
No generated text, letters, numbers, subtitles, logos or watermarks inside the AI-generated scene.
"""

NEGATIVE = (
    "blurry, low quality, distorted face, deformed body, extra limbs, bad anatomy, duplicate character, "
    "character morphing, face morphing, flicker, jitter, unstable clothing, unstable colors, random camera shake, "
    "extreme unwanted zoom, fisheye distortion, cropped head, cropped ears, subject out of frame, "
    "misshapen fruit, misshapen vegetable, duplicate objects, text, letters, numbers, subtitles, logo, watermark, "
    "horror, scary, violence, dark disturbing mood"
)


def gemini_learning_plan():
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is required")

    history = load_history()
    old_titles = [x.get("title", "") for x in history[-20:] if isinstance(x, dict)]
    item_text = json.dumps(DATA["items"], ensure_ascii=False)
    prompt = f"""
You are a senior preschool educational content director and cinematic animation director.
Create a highly entertaining educational SHORT, not a story.
CATEGORY: {CATEGORY}
LESSON: {DATA['lesson']}
EXACT ITEMS IN ORDER: {item_text}
MAIN VISUAL OBJECTS: {DATA['objects']}
AVOID OLD TITLES: {json.dumps(old_titles, ensure_ascii=False)}

The finished video is EXACTLY 10 seconds and has EXACTLY 3 scenes of about 3.3 seconds each.
Split the exact items into these fixed groups:
Scene 1 = items 1-3
Scene 2 = items 4-7
Scene 3 = items 8-10
Do not add, remove, reorder or rename any item.

The format is HOOK -> LEARN/COUNT -> FUN PAYOFF.
Use one adorable main cartoon animal, preferably a small bunny, with one fixed outfit.
The character should interact with the objects physically: hop, point, collect, bounce, reveal, clap, etc.
No complicated crowds. Maximum 2 characters.

CAMERA IS CRITICAL:
Scene 1: cinematic wide/high-angle establishing shot, then a gentle crane/aerial-style reveal toward the character.
Scene 2: smooth medium side-tracking/dolly or overhead counting shot with clear object movement.
Scene 3: energetic but stable hero/wide payoff, optionally gentle push-in at the end.
Specify framing, camera movement, depth/parallax, lens feel and lighting. Avoid generic 'zoom in'.

Return ONLY valid JSON:
{{
  "title":"short catchy Hindi title",
  "character":"fixed detailed appearance and outfit",
  "world":"fixed colorful environment",
  "hook":"very short Hindi hook",
  "scenes":[
    {{
      "items":["exact item strings from the assigned group"],
      "narration":"simple Hindi narration for this scene",
      "visual":"specific physical action involving the exact items",
      "camera":"specific cinematic shot, movement, framing, lens feel and depth",
      "lighting":"specific lighting",
      "transition":"visual continuity into next scene"
    }}
  ]
}}

Rules:
- Exactly 3 scenes.
- Scene 1 items exactly {json.dumps(DATA['items'][:3], ensure_ascii=False)}
- Scene 2 items exactly {json.dumps(DATA['items'][3:7], ensure_ascii=False)}
- Scene 3 items exactly {json.dumps(DATA['items'][7:10], ensure_ascii=False)}
- Preschool-friendly, cheerful, educational and visually exciting.
- Keep object counts/identity physically clear.
- No written text inside generated imagery.
"""

    client = genai.Client(api_key=GEMINI_KEY)
    last_error = None
    for model in [GEMINI_MODEL, GEMINI_FALLBACK]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.75, response_mime_type="application/json"),
            )
            data = json.loads(response.text)
            scenes = data.get("scenes", [])
            if len(scenes) != 3:
                raise ValueError(f"Gemini returned {len(scenes)} scenes")
            expected = [DATA["items"][:3], DATA["items"][3:7], DATA["items"][7:10]]
            for i, scene in enumerate(scenes):
                scene["items"] = expected[i]
                scene.setdefault("narration", "")
                scene.setdefault("visual", "")
                scene.setdefault("camera", "cinematic medium tracking shot")
                scene.setdefault("lighting", "soft warm cinematic light")
                scene.setdefault("transition", "natural continuous movement")
            data["category"] = CATEGORY
            data["exact_items"] = DATA["items"]
            data["character"] = str(data.get("character", "cute white bunny with a yellow shirt"))
            data["world"] = str(data.get("world", "bright magical fruit garden"))
            print(f"🧠 Gemini learning plan: {data['title']} ({model})")
            return data
        except Exception as exc:
            last_error = exc
            print(f"⚠️ Gemini model {model} failed: {exc}")
            time.sleep(1)
    raise RuntimeError(f"Gemini learning plan failed: {last_error}")


def pixazo_request(prompt, index):
    if not PIXAZO_KEY:
        raise RuntimeError("PIXAZO_API_KEY is not set")
    url = f"{API_BASE}/ltx-video/v1/text-to-video"
    headers = {"Content-Type": "application/json", "Ocp-Apim-Subscription-Key": PIXAZO_KEY}
    payload = {
        "prompt": prompt,
        "negative": NEGATIVE,
        "aspect": "9:16",
        "num_frames": 81,
        "frame_rate": 24,
        "steps": 8,
        "cfg": 3.0,
    }
    print(f"🎬 Pixazo FREE LTX scene {index + 1}/3")
    r = requests.post(url, headers=headers, json=payload, timeout=90)
    if r.status_code >= 400:
        raise RuntimeError(f"Pixazo HTTP {r.status_code}: {r.text[:1500]}")
    data = r.json()
    request_id = data.get("request_id") if isinstance(data, dict) else None
    polling_url = data.get("polling_url") if isinstance(data, dict) else None
    if not request_id:
        raise RuntimeError(f"Pixazo returned no request_id: {data}")
    status_url = polling_url or f"{API_BASE}/v2/requests/status/{request_id}"
    print(f"   request_id={request_id}")
    for poll_no in range(1, 301):
        time.sleep(5)
        sr = requests.get(status_url, headers={"Ocp-Apim-Subscription-Key": PIXAZO_KEY}, timeout=45)
        if sr.status_code >= 400:
            raise RuntimeError(f"Pixazo status HTTP {sr.status_code}: {sr.text[:1500]}")
        sd = sr.json()
        status = str(sd.get("status", "")).upper()
        elapsed = poll_no * 5 / 60
        if poll_no == 1 or poll_no % 12 == 0 or status not in ("PROCESSING", "QUEUED"):
            print(f"   Pixazo status: {status} ({elapsed:.1f} min)")
        if status == "COMPLETED":
            output = sd.get("output", {})
            media = output.get("media_url") if isinstance(output, dict) else None
            if isinstance(media, list) and media:
                return media[0]
            if isinstance(media, str):
                return media
            raise RuntimeError(f"Pixazo completed without media URL: {sd}")
        if status in ("ERROR", "FAILED", "CANCELLED"):
            raise RuntimeError(f"Pixazo generation failed: {sd}")
    raise TimeoutError("Pixazo generation timed out after 25 minutes")


def download(url, path):
    print("⬇️ Downloading Pixazo video")
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    path.write_bytes(r.content)
    if path.stat().st_size < 10000:
        raise RuntimeError(f"Downloaded Pixazo file looks invalid: {path}")


def scene_prompt(plan, scene, index):
    shot_plan = [
        "START WIDE: beautiful high-angle establishing view of the world, then a slow cinematic crane/aerial-style reveal toward the full-body character. Show foreground depth and many environmental layers.",
        "ACTION TRACK: smooth medium side-dolly/tracking shot or gentle overhead angle following the character as it physically counts/collects/reveals the objects. Strong parallax, readable full body.",
        "HERO PAYOFF: energetic but controlled medium-wide hero shot with all final objects visible, then a gentle cinematic push toward the happy character. Finish on a clean celebratory composition."
    ][index]
    return (
        f"{CINEMATIC_BIBLE}\nCATEGORY: {CATEGORY}\nLESSON: {DATA['lesson']}\n"
        f"FIXED CHARACTER: {plan.get('character','cute bunny')}\nFIXED WORLD: {plan.get('world','bright colorful garden')}\n"
        f"EXACT LEARNING ITEMS FOR THIS SCENE: {json.dumps(scene.get('items', []), ensure_ascii=False)}\n"
        f"SCENE ACTION: {scene.get('visual','')}\nCAMERA DIRECTOR NOTE: {scene.get('camera','')}\nSHOT PLAN: {shot_plan}\n"
        f"LIGHTING: {scene.get('lighting','soft warm cinematic light')}\nCONTINUITY: {scene.get('transition','natural continuous movement')}\n"
        "Make every learning object large, recognizable, colorful and physically plausible. Objects must not morph. "
        "The AI scene itself must contain NO text, letters, numbers, subtitles, signs, logos or watermark."
    )


# Burn exact learning labels ourselves; never ask the video model to render text.
def make_learning_ass(scenes, path):
    def ts(x):
        m = int(x // 60)
        s = x - m * 60
        return f"0:{m:02d}:{s:05.2f}"

    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Learn,Noto Sans Devanagari,62,&H00FFFFFF,&H00FFFFFF,&H0015222D,&H99000000,1,0,0,0,100,100,0,0,1,4,2,2,55,55,180,1",
        "Style: Big,Noto Sans,104,&H00FFFFFF,&H00FFFFFF,&H0015222D,&HAA000000,1,0,0,0,100,100,0,0,1,6,3,5,40,40,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    start = 0.0
    for scene, slot in zip(scenes, SLOTS):
        end = min(10.0, start + slot)
        narration = str(scene.get("narration", "")).replace("{", "(").replace("}", ")")
        items = scene.get("items", [])
        if CATEGORY == "numbers":
            label = "  •  ".join(items)
        else:
            label = "  •  ".join(items)
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Big,,0,0,0,,{label}")
        lines.append(f"Dialogue: 1,{ts(start)},{ts(end)},Learn,,0,0,0,,{narration}")
        start = end
    path.write_text("\n".join(lines), encoding="utf-8")


async def tts(text, path):
    await edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate="+8%").save(str(path))


def main():
    WORK.mkdir(exist_ok=True)
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is required for the educational cinematic pipeline")
    if not PIXAZO_KEY:
        raise RuntimeError("PIXAZO_API_KEY secret is required")

    plan = gemini_learning_plan()
    scenes = plan["scenes"]
    print(f"📚 Category: {CATEGORY}")
    print(f"📖 {plan['title']}")
    META.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    clips = []
    for i, scene in enumerate(scenes):
        raw = WORK / f"pixazo_learning_clip_raw_{i}.mp4"
        url = pixazo_request(scene_prompt(plan, scene, i), i)
        download(url, raw)
        clips.append(raw)

    voices, sfxs = [], []
    for i, scene in enumerate(scenes):
        raw_voice = WORK / f"pixazo_learning_voice_raw_{i}.mp3"
        voice = WORK / f"pixazo_learning_voice_{i}.m4a"
        fx = WORK / f"pixazo_learning_sfx_{i}.wav"
        asyncio.run(tts(scene.get("narration", ""), raw_voice))
        fit_voice(raw_voice, voice, SLOTS[i])
        make_sfx(fx, sfx_kind(scene))
        voices.append(voice)
        sfxs.append(fx)

    video = WORK / "pixazo_learning_video.mp4"
    assemble(clips, video)
    music = WORK / "pixazo_learning_music.wav"
    make_music(music)
    ass = WORK / "pixazo_learning_subtitles.ass"
    make_learning_ass(scenes, ass)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    mux(video, music, voices, sfxs, ass, OUT)
    print(f"✅ Pixazo + Gemini educational video: {OUT}")
    print(f"📝 Learning metadata: {META}")


if __name__ == "__main__":
    main()
