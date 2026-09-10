import asyncio
import base64
import json
import os
import time
import wave
from pathlib import Path

import requests
from google import genai
from google.genai import types

import hf_wan_10sec_story_av_v2 as av
from toon_kids_story import WORK, load_history

PIXAZO_KEY = os.getenv("PIXAZO_API_KEY", "").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
CATEGORY = os.getenv("CONTENT_CATEGORY", "numbers").strip().lower()
OUT = Path(os.getenv("PIXAZO_OUTPUT", "toon_pixazo_ltx_20sec_rhyme.mp4"))
META = Path(os.getenv("PIXAZO_METADATA", "pixazo_rhyme_metadata.json"))
API_BASE = "https://gateway.pixazo.ai"

# Rhyme format: 4 x 5-second musical scenes = 20 seconds.
SLOTS = [5.0, 5.0, 5.0, 5.0]
av.SLOTS = SLOTS
av.FINAL_SECONDS = 20.0

CATEGORY_DATA = {
    "numbers": {
        "title": "सेबों वाली गिनती",
        "items": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
        "objects": "large shiny red, yellow and orange apples",
        "lesson": "बच्चों को 1 से 10 तक गिनना सिखाना",
    },
    "fruits": {
        "title": "फलों की मस्ती वाली कविता",
        "items": ["सेब", "केला", "आम", "संतरा", "स्ट्रॉबेरी", "अंगूर", "तरबूज", "अनानास", "नाशपाती", "पपीता"],
        "objects": "large bright colorful fruits",
        "lesson": "बच्चों को फलों के नाम पहचानना सिखाना",
    },
    "vegetables": {
        "title": "सब्जियों की मस्ती वाली कविता",
        "items": ["गाजर", "टमाटर", "आलू", "मटर", "भिंडी", "बैंगन", "मक्का", "फूलगोभी", "पालक", "कद्दू"],
        "objects": "large bright colorful vegetables",
        "lesson": "बच्चों को सब्जियों के नाम पहचानना सिखाना",
    },
}

if CATEGORY not in CATEGORY_DATA:
    CATEGORY = "numbers"
DATA = CATEGORY_DATA[CATEGORY]

CHARACTER = (
    "one single adorable small WHITE BUNNY, round fluffy face, big blue eyes, "
    "long upright white ears with pink inner ears, tiny pink nose, rosy cheeks, "
    "short fluffy tail, EXACT SAME royal-blue overalls, bright yellow bow tie and tiny brown shoes"
)
WORLD = (
    "the EXACT SAME sunny magical apple garden, green grass, colorful flowers, apple trees, "
    "soft hills, warm golden daylight, playful rainbow-colored bunting and a tiny wooden bridge"
)

CINEMATIC_BIBLE = """
Premium polished 3D animated nursery-rhyme music video for preschool children.
Think modern high-quality kids-song production: catchy, colorful, joyful, musical, playful and easy to follow.
This is a RHYME / SONG PERFORMANCE, not a lecture and not a dry educational explainer.
The character should dance, clap, bounce, point, spin and react to the beat.
Learning objects should bounce, roll, sparkle and arrange themselves in clear patterns.
Use visual variety every few seconds: wide dance shot, medium action, overhead reveal, gentle push-in,
side tracking and celebratory hero framing. Never use frantic camera movement.
Keep one consistent character, outfit, world and art style across every scene.
Vertical 9:16, polished animated-film lighting, rich colors, soft depth of field, readable silhouettes.
No generated text, letters, numbers, subtitles, logos or watermarks inside the AI scene.
"""

NEGATIVE = (
    "boring static shot, lecture, slow lifeless movement, frantic motion, rapid cuts, time lapse, speed ramp, "
    "camera shake, extreme zoom, fisheye, blurry, low quality, distorted face, deformed body, extra limbs, "
    "bad anatomy, duplicate character, character morphing, face morphing, flicker, jitter, unstable clothing, "
    "unstable colors, cropped head, cropped ears, subject out of frame, second character, crowd, other animals, "
    "sheep, goat, mouse, rat, hamster, cat, dog, fox, monkey, misshapen fruit, duplicate objects, floating objects, "
    "text, letters, numbers, subtitles, logo, watermark, horror, scary, violence, dark disturbing mood"
)

RHYME_LYRICS = [
    "एक लाल सेब, दो लाल सेब, तीन सेब मुस्काएँ!\nताली बजाओ, झूमो गाओ, गिनती गीत सुनाएँ!",
    "चार, पाँच, छह — वाह भई वाह!\nसेबों संग नाचो, गिनती गाओ, हा हा हा!",
    "सात, आठ, नौ — झूमो साथ!\nनौ से आगे चल पड़े, दस है हमारे पास!",
    "दस! दस! पूरे दस! — ताली ताली नाचो!\nएक से दस फिर गाएँ, फिर से मस्ती मचाओ!",
]


def gemini_rhyme_plan():
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is required")
    history = load_history()
    old_titles = [x.get("title", "") for x in history[-20:] if isinstance(x, dict)]
    prompt = f"""
You are a senior preschool nursery-rhyme director.
Design a catchy ORIGINAL Hindi educational counting song, inspired by the GENERAL FORMAT of modern kids channels:
repetition, sing-along rhythm, dancing, cute character acting, colorful objects, simple learning and a happy payoff.
Do NOT copy any existing song, lyrics, characters, channel branding or distinctive scene.

CATEGORY: {CATEGORY}
LESSON: {DATA['lesson']}
EXACT ITEMS: {json.dumps(DATA['items'], ensure_ascii=False)}
FIXED CHARACTER: {CHARACTER}
FIXED WORLD: {WORLD}
OLD TITLES TO AVOID: {json.dumps(old_titles, ensure_ascii=False)}

Make EXACTLY 4 scenes, 5 seconds each. This is a 20-second SHORT.
Scene 1: 1,2,3 — musical hook + bunny dance + apples bounce.
Scene 2: 4,5,6 — playful counting + bunny claps and dances.
Scene 3: 7,8,9 — playful build-up + camera movement + apples form a fun pattern.
Scene 4: 10 + repeat 1-10 feeling — big celebratory finish with bunny dancing.

The lyrics must be short, rhythmic, repetitive and easy for a 2-6 year old to sing along with.
Use simple Hindi and rhyme-like endings. Do not cram explanations.
Visuals must clearly teach the numbers while feeling like a SONG PERFORMANCE.

Return only JSON:
{{"title":"catchy original Hindi title","scenes":[
 {{"items":[],"lyrics":"","visual":"","camera":"","beat":""}},
 {{"items":[],"lyrics":"","visual":"","camera":"","beat":""}},
 {{"items":[],"lyrics":"","visual":"","camera":"","beat":""}},
 {{"items":[],"lyrics":"","visual":"","camera":"","beat":""}}
]}}
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
            if len(scenes) != 4:
                raise ValueError(f"Gemini returned {len(scenes)} scenes")
            expected = [DATA["items"][:3], DATA["items"][3:6], DATA["items"][6:9], DATA["items"][9:10]]
            for i, scene in enumerate(scenes):
                scene["items"] = expected[i]
                # Numbers rhyme is deterministic so every generated video remains educationally correct.
                scene["lyrics"] = RHYME_LYRICS[i] if CATEGORY == "numbers" else str(scene.get("lyrics", "चलो गाएँ और सीखें!"))
                scene.setdefault("visual", "bunny dances and points to the learning objects in rhythm")
                scene.setdefault("camera", "stable colorful medium-wide musical performance shot")
                scene.setdefault("beat", "upbeat preschool bounce")
            data["category"] = CATEGORY
            data["exact_items"] = DATA["items"]
            data["character"] = CHARACTER
            data["world"] = WORLD
            data["format"] = "original Hindi nursery rhyme, 4x5-second musical scenes"
            print(f"🎵 Gemini rhyme plan: {data.get('title', DATA['title'])} ({model})")
            return data
        except Exception as exc:
            last_error = exc
            print(f"⚠️ Gemini model {model} failed: {exc}")
            time.sleep(1)
    raise RuntimeError(f"Gemini rhyme plan failed: {last_error}")


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
    print(f"🎬 Pixazo FREE LTX rhyme scene {index + 1}/4 (5 sec)")
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
    item_text = json.dumps(scene.get("items", []), ensure_ascii=False)
    shots = [
        "OPENING MUSICAL HOOK: wide colorful garden, bunny enters dancing, apples bounce to the beat. Gentle lateral camera move, full body visible.",
        "DANCE-AND-COUNT: medium-wide side tracking shot. Bunny claps and hops in a simple 1-2 beat while each apple rolls/bounces into place. Add playful parallax.",
        "BUILD-UP: slightly elevated overhead reveal then smooth arc. Apples arrange into a playful curved pattern while bunny points, spins once and laughs. Keep motion readable.",
        "BIG FINALE: bright wide hero shot. Bunny dances and claps with the final apple, then all ten apples are visible in a neat colorful semicircle for a joyful payoff. Gentle push-in only at the end.",
    ][index]
    return (
        f"{CINEMATIC_BIBLE}\n"
        f"FIXED CHARACTER — ABSOLUTE: {CHARACTER}\n"
        f"FIXED WORLD — ABSOLUTE: {WORLD}\n"
        f"SCENE {index+1}/4. LEARNING ITEMS: {item_text}\n"
        f"MUSICAL ACTION: {scene.get('visual','')}\n"
        f"SHOT DIRECTOR: {shots}\n"
        f"BEAT: {scene.get('beat','upbeat preschool bounce')}\n"
        "ABSOLUTE CONTINUITY: one bunny only, same face, ears, overalls, bow tie, shoes and proportions; same garden. "
        "For number scenes, show the requested number of large apples clearly and physically plausibly. "
        "The AI-generated scene itself must contain NO text, letters, numbers, subtitles, signs, logos or watermark."
    )


def save_pcm_wav(path, pcm, rate=24000):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def gemini_rhyme_tts(text, path):
    """Free-tier Gemini TTS: expressive sing-song nursery-rhyme delivery."""
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = (
        "Perform this original Hindi nursery-rhyme lyric like a cheerful preschool children's song. "
        "Use a bright, playful, rhythmic sing-song delivery with clear Hindi pronunciation, little pauses "
        "between counting words, smiling energy, and a simple bouncy melody-like cadence. "
        "Do not speak like a news narrator. Keep the words exactly as written.\n\n" + text
    )
    response = client.models.generate_content(
        model=GEMINI_TTS_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
                )
            ),
        ),
    )
    part = response.candidates[0].content.parts[0]
    data = part.inline_data.data
    if isinstance(data, str):
        data = base64.b64decode(data)
    save_pcm_wav(path, data, 24000)


def make_learning_ass(scenes, path):
    def ts(x):
        m = int(x // 60)
        s = x - m * 60
        return f"0:{m:02d}:{s:05.2f}"

    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Learn,Noto Sans Devanagari,54,&H00FFFFFF,&H00FFFFFF,&H0015222D,&H99000000,1,0,0,0,100,100,0,0,1,4,2,2,55,55,145,1",
        "Style: Big,Noto Sans,92,&H00FFFFFF,&H00FFFFFF,&H0015222D,&HAA000000,1,0,0,0,100,100,0,0,1,6,3,5,40,40,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    start = 0.0
    for scene, slot in zip(scenes, SLOTS):
        end = min(20.0, start + slot)
        lyrics = str(scene.get("lyrics", "")).replace("{", "(").replace("}", ")").replace("\n", "\\N")
        label = "  •  ".join(str(x) for x in scene.get("items", []))
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Big,,0,0,0,,{label}")
        lines.append(f"Dialogue: 1,{ts(start)},{ts(end)},Learn,,0,0,0,,{lyrics}")
        start = end
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    WORK.mkdir(exist_ok=True)
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is required")
    if not PIXAZO_KEY:
        raise RuntimeError("PIXAZO_API_KEY secret is required")

    plan = gemini_rhyme_plan()
    scenes = plan["scenes"]
    META.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    clips = []
    for i, scene in enumerate(scenes):
        raw = WORK / f"pixazo_rhyme_scene_{i+1}.mp4"
        url = pixazo_request(scene_prompt(plan, scene, i), i)
        download(url, raw)
        clips.append(raw)

    silent = WORK / "pixazo_rhyme_silent.mp4"
    av.assemble(clips, silent)

    voices = []
    sfxs = []
    for i, scene in enumerate(scenes):
        voice = WORK / f"pixazo_rhyme_voice_{i+1}.wav"
        try:
            gemini_rhyme_tts(str(scene.get("lyrics", "")), voice)
            print(f"🎤 Gemini 3.1 Flash TTS scene {i+1}: sing-song mode")
        except Exception as exc:
            print(f"⚠️ Gemini TTS failed, using fallback: {exc}")
            import edge_tts
            asyncio.run(edge_tts.Communicate(text=str(scene.get("lyrics", "")), voice="hi-IN-SwaraNeural", rate="-3%").save(str(voice)))

        fitted = WORK / f"pixazo_rhyme_voice_{i+1}_fit.m4a"
        av.fit_voice(voice, fitted, SLOTS[i])
        voices.append(fitted)

        sfx = WORK / f"pixazo_rhyme_sfx_{i+1}.wav"
        av.make_sfx(sfx, "sparkle" if i == 3 else "pop")
        sfxs.append(sfx)

    music = WORK / "pixazo_rhyme_music.wav"
    av.make_music(music)

    ass = WORK / "pixazo_rhyme.ass"
    make_learning_ass(scenes, ass)
    av.mux(silent, music, voices, sfxs, ass, OUT)

    if not OUT.exists() or OUT.stat().st_size < 10000:
        raise RuntimeError(f"Final video missing/invalid: {OUT}")
    print(f"✅ FINAL RHYME: {OUT} ({OUT.stat().st_size / 1024 / 1024:.1f} MB)")
    print("✅ 20 sec | 4 musical scenes | Gemini expressive TTS | 24fps | 9:16")


if __name__ == "__main__":
    main()
