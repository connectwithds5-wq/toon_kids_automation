import asyncio
import json
import os
import time
from pathlib import Path

import requests
import edge_tts
from google import genai
from google.genai import types

import hf_wan_10sec_story_av_v2 as av
from toon_kids_story import WORK, load_history

PIXAZO_KEY = os.getenv("PIXAZO_API_KEY", "").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
CATEGORY = os.getenv("CONTENT_CATEGORY", "numbers").strip().lower()
OUT = Path(os.getenv("PIXAZO_OUTPUT", "toon_pixazo_ltx_10sec_learning.mp4"))
META = Path(os.getenv("PIXAZO_METADATA", "pixazo_learning_metadata.json"))
API_BASE = "https://gateway.pixazo.ai"

# Slower, calmer educational pacing: only TWO 5-second scenes.
SLOTS = [5.0, 5.0]
av.SLOTS = SLOTS
av.FINAL_SECONDS = 10.0

CATEGORY_DATA = {
    "numbers": {
        "title": "1 से 10 गिनती",
        "items": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
        "objects": "large shiny red and yellow apples",
        "lesson": "बच्चों को 1 से 10 तक गिनना सिखाना",
    },
    "fruits": {
        "title": "मजेदार फलों की पहचान",
        "items": ["सेब", "केला", "आम", "संतरा", "स्ट्रॉबेरी", "अंगूर", "तरबूज", "अनानास", "नाशपाती", "पपीता"],
        "objects": "large bright colorful fruits",
        "lesson": "बच्चों को फलों के नाम पहचानना सिखाना",
    },
    "vegetables": {
        "title": "रंगीन सब्जियाँ",
        "items": ["गाजर", "टमाटर", "आलू", "मटर", "भिंडी", "बैंगन", "मक्का", "फूलगोभी", "पालक", "कद्दू"],
        "objects": "large bright colorful vegetables",
        "lesson": "बच्चों को सब्जियों के नाम पहचानना सिखाना",
    },
}

if CATEGORY not in CATEGORY_DATA:
    CATEGORY = "numbers"
DATA = CATEGORY_DATA[CATEGORY]

# HARD-LOCK the visual identity. Do not let Gemini invent a new animal per scene.
CHARACTER = (
    "one single adorable small WHITE BUNNY, round fluffy face, big blue eyes, "
    "long upright white ears with pink inner ears, tiny pink nose, rosy cheeks, "
    "short fluffy tail, wearing the EXACT SAME royal-blue overalls, bright yellow bow tie "
    "and tiny brown shoes in every scene"
)
WORLD = (
    "the EXACT SAME sunny magical apple garden in both scenes, green grass, "
    "flower patches, apple trees, warm golden morning light, colorful flowers, soft distant hills"
)

CINEMATIC_BIBLE = """
Premium polished 3D animated-feature-quality preschool cartoon.
This is a calm, playful educational short, NOT a fast montage.
Use one single character only and preserve identity exactly.
Use readable physical actions, gentle body movement and deliberate camera motion.
Prefer medium-wide and wide framing; do not spend the whole shot on a face close-up.
Vertical 9:16 composition, safe margins, rich colorful environment, soft believable lighting,
cinematic depth of field, clean polished materials, smooth natural animation.
No generated text, letters, numbers, subtitles, signs, logos or watermarks inside the AI scene.
"""

NEGATIVE = (
    "fast action, frantic motion, rapid cuts, time lapse, speed ramp, camera shake, extreme zoom, fisheye, "
    "blurry, low quality, distorted face, deformed body, extra limbs, bad anatomy, duplicate character, "
    "character morphing, face morphing, flicker, jitter, unstable clothing, unstable colors, cropped head, "
    "cropped ears, subject out of frame, sheep, lamb, goat, mouse, rat, hamster, bear, cat, dog, fox, monkey, "
    "second character, crowd, extra animal, misshapen apple, duplicate objects, floating objects, text, letters, "
    "numbers, subtitles, logo, watermark, horror, scary, violence, dark disturbing mood"
)


def gemini_learning_plan():
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is required")

    history = load_history()
    old_titles = [x.get("title", "") for x in history[-20:] if isinstance(x, dict)]
    prompt = f"""
You are directing a premium preschool educational short.
Create a FUN, CALM, EASY-TO-FOLLOW 10-second learning video.
This is NOT a story and NOT a rapid montage.
CATEGORY: {CATEGORY}
LESSON: {DATA['lesson']}
EXACT ITEMS IN ORDER: {json.dumps(DATA['items'], ensure_ascii=False)}
OLD TITLES TO AVOID: {json.dumps(old_titles, ensure_ascii=False)}

There are EXACTLY TWO scenes, 5 seconds each:
Scene 1 teaches items 1-5.
Scene 2 teaches items 6-10.

The main character is FIXED and MUST NOT be changed:
{CHARACTER}
There must be NO other animal or person.
The world is FIXED and MUST NOT change:
{WORLD}

PACING:
- Slow enough for a preschool child to understand.
- One clear physical action at a time.
- Use a tiny playful reaction at the end of each scene.
- Avoid frantic hopping, rapid object spawning, rapid camera movement or excessive close-ups.

For each scene give a short Hindi narration that can be spoken comfortably in about 4 seconds.
Use natural counting with pauses, for example: "एक... दो... तीन... चार... पाँच! वाह!"
Do not cram extra teaching words into the narration.

CAMERA:
Scene 1: 5-second medium-wide establishing shot, gentle lateral dolly, bunny clearly visible full-body while it points to/collects five apples one by one; finish with a small happy clap.
Scene 2: 5-second medium-wide continuation in the SAME garden, gentle arc/orbit, bunny reveals the next five apples and finishes with a cheerful bounce; stable camera, no sudden zoom.

Return ONLY JSON with:
{{
 "title":"short catchy Hindi title",
 "hook":"very short Hindi hook",
 "scenes":[
   {{"items":[],"narration":"","visual":"","camera":"","lighting":""}},
   {{"items":[],"narration":"","visual":"","camera":"","lighting":""}}
 ]
}}
"""

    client = genai.Client(api_key=GEMINI_KEY)
    last_error = None
    for model in [GEMINI_MODEL, GEMINI_FALLBACK]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            data = json.loads(response.text)
            scenes = data.get("scenes", [])
            if len(scenes) != 2:
                raise ValueError(f"Gemini returned {len(scenes)} scenes")

            expected = [DATA["items"][:5], DATA["items"][5:10]]
            narrations = [
                "एक... दो... तीन... चार... पाँच! वाह, कितने सारे सेब!",
                "छह... सात... आठ... नौ... दस! दस पूरे! शाबाश!",
            ] if CATEGORY == "numbers" else None

            for i, scene in enumerate(scenes):
                scene["items"] = expected[i]
                # For counting, deterministic narration is better than AI-generated rushed prose.
                if narrations:
                    scene["narration"] = narrations[i]
                else:
                    scene.setdefault("narration", "चलो सीखें! बहुत बढ़िया!")
                scene.setdefault("visual", "slowly point to and collect the objects one by one")
                scene.setdefault("camera", "stable medium-wide gentle dolly, full body visible")
                scene.setdefault("lighting", "warm soft morning light")

            data["category"] = CATEGORY
            data["exact_items"] = DATA["items"]
            data["character"] = CHARACTER
            data["world"] = WORLD
            data["pacing"] = "slow educational 2x5-second scenes"
            print(f"🧠 Gemini learning plan: {data.get('title', DATA['title'])} ({model})")
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
        "num_frames": 121,
        "frame_rate": 24,
        "steps": 8,
        "cfg": 3.0,
    }
    print(f"🎬 Pixazo FREE LTX scene {index + 1}/2 (5 seconds, calm pacing)")
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
    groups = ["FIRST FIVE", "SECOND FIVE"]
    if index == 0:
        shot = (
            "5-SECOND SINGLE CONTINUOUS SHOT. Start medium-wide with the bunny full body and the garden clearly visible. "
            "Use a very gentle side dolly while the bunny slowly points to five large apples in sequence, one at a time. "
            "Keep the bunny centered and readable. End with a tiny happy clap. No fast movement, no cuts."
        )
    else:
        shot = (
            "5-SECOND SINGLE CONTINUOUS SHOT. Continue in the SAME garden with the SAME bunny. "
            "Use a gentle stable camera arc around the bunny as it calmly reveals five more large apples in sequence. "
            "Keep all five apples readable and finish with one cheerful small bounce. No fast movement, no cuts."
        )

    return (
        f"{CINEMATIC_BIBLE}\n"
        f"FIXED CHARACTER — ABSOLUTE: {CHARACTER}\n"
        f"FIXED WORLD — ABSOLUTE: {WORLD}\n"
        f"THIS IS SCENE {index+1} OF 2 ({groups[index]}).\n"
        f"EXACT LEARNING ITEMS: {json.dumps(scene.get('items', []), ensure_ascii=False)}\n"
        f"ACTION: {scene.get('visual', '')}\n"
        f"CAMERA: {shot}\n"
        f"LIGHTING: {scene.get('lighting', 'warm soft morning light')}\n"
        "ABSOLUTE CONTINUITY: The only character is the white bunny described above. Do not introduce, replace, "
        "or transform it into any other species. Same face, same ears, same blue overalls, same yellow bow tie, "
        "same brown shoes, same colors, same proportions. Same garden.\n"
        "Make exactly five large, recognizable apples visible in this scene. They stay solid and physically plausible. "
        "The AI scene itself must contain NO text, letters, numbers, subtitles, signs, logos or watermark."
    )


def make_learning_ass(scenes, path):
    def ts(x):
        m = int(x // 60)
        s = x - m * 60
        return f"0:{m:02d}:{s:05.2f}"

    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Learn,Noto Sans Devanagari,58,&H00FFFFFF,&H00FFFFFF,&H0015222D,&H99000000,1,0,0,0,100,100,0,0,1,4,2,2,55,55,170,1",
        "Style: Big,Noto Sans,96,&H00FFFFFF,&H00FFFFFF,&H0015222D,&HAA000000,1,0,0,0,100,100,0,0,1,6,3,5,40,40,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    start = 0.0
    for scene, slot in zip(scenes, SLOTS):
        end = min(10.0, start + slot)
        narration = str(scene.get("narration", "")).replace("{", "(").replace("}", ")")
        label = "  •  ".join(str(x) for x in scene.get("items", []))
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Big,,0,0,0,,{label}")
        lines.append(f"Dialogue: 1,{ts(start)},{ts(end)},Learn,,0,0,0,,{narration}")
        start = end
    path.write_text("\n".join(lines), encoding="utf-8")


async def tts(text, path):
    # Deliberately slower than the previous +8% setting.
    await edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate="-15%").save(str(path))


def main():
    WORK.mkdir(exist_ok=True)
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is required for the educational cinematic pipeline")
    if not PIXAZO_KEY:
        raise RuntimeError("PIXAZO_API_KEY secret is required")

    plan = gemini_learning_plan()
    scenes = plan["scenes"]
    META.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    clips = []
    for i, scene in enumerate(scenes):
        raw = WORK / f"pixazo_learning_scene_{i+1}.mp4"
        url = pixazo_request(scene_prompt(plan, scene, i), i)
        download(url, raw)
        clips.append(raw)

    # Keep the final assembly exactly 10 seconds at 24fps.
    silent = WORK / "pixazo_learning_silent.mp4"
    av.assemble(clips, silent)

    voices = []
    sfxs = []
    for i, scene in enumerate(scenes):
        voice = WORK / f"pixazo_learning_voice_{i+1}.mp3"
        asyncio.run(tts(str(scene.get("narration", "")), voice))
        fitted = WORK / f"pixazo_learning_voice_{i+1}_fit.m4a"
        av.fit_voice(voice, fitted, SLOTS[i])
        voices.append(fitted)

        sfx = WORK / f"pixazo_learning_sfx_{i+1}.wav"
        av.make_sfx(sfx, "pop" if i == 0 else "sparkle")
        sfxs.append(sfx)

    music = WORK / "pixazo_learning_music.wav"
    av.make_music(music)

    ass = WORK / "pixazo_learning.ass"
    make_learning_ass(scenes, ass)
    av.mux(silent, music, voices, sfxs, ass, OUT)

    if not OUT.exists() or OUT.stat().st_size < 10000:
        raise RuntimeError(f"Final video missing/invalid: {OUT}")
    print(f"✅ FINAL: {OUT} ({OUT.stat().st_size / 1024 / 1024:.1f} MB)")
    print("✅ Pacing: 2 scenes × 5 seconds | 24fps | slow Hindi narration | fixed bunny")


if __name__ == "__main__":
    main()
