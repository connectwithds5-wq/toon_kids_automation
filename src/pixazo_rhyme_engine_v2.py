import asyncio
import base64
import json
import math
import os
import subprocess
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

BPM = 124
BEAT = 60.0 / BPM
SLOTS = [5.0, 5.0, 5.0, 5.0]
TOTAL = 20.0
FPS = 24
W, H = 1080, 1920

CATEGORY_DATA = {
    "numbers": {"title": "सेब गिनो, नाचो!", "items": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"], "objects": "large shiny red, yellow and orange apples", "lesson": "1 से 10 तक गिनती"},
    "fruits": {"title": "फलों की झूमती मस्ती", "items": ["सेब", "केला", "आम", "संतरा", "स्ट्रॉबेरी", "अंगूर", "तरबूज", "अनानास", "नाशपाती", "पपीता"], "objects": "large bright colorful fruits", "lesson": "फलों के नाम"},
    "vegetables": {"title": "सब्जियों की धूम", "items": ["गाजर", "टमाटर", "आलू", "मटर", "भिंडी", "बैंगन", "मक्का", "फूलगोभी", "पालक", "कद्दू"], "objects": "large bright colorful vegetables", "lesson": "सब्जियों के नाम"},
    "colors": {"title": "रंगों की रेलमपेल", "items": ["लाल", "पीला", "नीला", "हरा", "नारंगी", "गुलाबी", "बैंगनी", "भूरा", "सफेद", "काला"], "objects": "large glossy colorful toy balls", "lesson": "रंगों के नाम"},
    "animals": {"title": "जानवरों की झूम-झूम", "items": ["शेर", "हाथी", "बंदर", "गाय", "घोड़ा", "कुत्ता", "बिल्ली", "खरगोश", "बतख", "भालू"], "objects": "cute toy animal figures", "lesson": "जानवरों के नाम"},
}
if CATEGORY not in CATEGORY_DATA:
    CATEGORY = "numbers"
DATA = CATEGORY_DATA[CATEGORY]

CHARACTER = "ONE single adorable small white bunny, round fluffy face, big blue eyes, long upright white ears with pink inner ears, tiny pink nose, rosy cheeks, short fluffy tail, EXACT royal-blue overalls, bright yellow bow tie and tiny brown shoes. This exact character is locked across all four clips."
WORLD = "ONE locked sunny magical preschool garden: green grass, colorful flowers, a few friendly apple trees, soft hills, warm golden daylight, rainbow bunting and a tiny wooden bridge. Same layout and lighting throughout."

NEGATIVE = "text, letters, numbers, subtitles, captions, signs, logos, watermark, writing, generated typography, second character, crowd, extra animal, duplicate bunny, duplicate character, character morphing, face morphing, species change, clothing change, color change, extra limbs, bad anatomy, deformed face, broken hands, flicker, jitter, unstable identity, unstable background, object duplication, floating objects, blurry, low quality, static pose, lecture, classroom, slideshow, frantic motion, rapid cuts, camera shake, extreme zoom, fisheye, horror, dark mood"

NUMBER_LYRICS = [
    "एक, दो, तीन!\nटप-टप-टप, चलो नाचें तीन!",
    "चार, पाँच, छह!\nताली बजाओ, झूमो छह!",
    "सात, आठ, नौ!\nकूदो-घूमो, हँसो नौ!",
    "दस! दस! दस!\nएक से दस, फिर से मस्त!",
]

FIXED_VISUAL_BEATS = [
    "Beat 1: bunny hops into frame and waves. Beat 2: FIRST prop pops in. Beat 3: SECOND prop pops in. Beat 4: THIRD prop pops in. Beat 5: bunny claps and all three bounce together.",
    "Beat 1: bunny claps twice. Beat 2: FOURTH prop rolls in. Beat 3: FIFTH prop rolls in. Beat 4: SIXTH prop rolls in. Beat 5: bunny side-steps and all six visible props bounce once.",
    "Beat 1: bunny points left. Beat 2: SEVENTH prop arcs in. Beat 3: EIGHTH prop arcs in. Beat 4: NINTH prop arcs in. Beat 5: bunny spins once and the three new props sparkle.",
    "Beat 1: bunny jumps. Beat 2: TENTH prop makes a joyful bounce entrance. Beat 3: bunny claps. Beat 4: all ten learning props arrange into a clean semicircle. Beat 5: bunny celebrates with a big wave and smile.",
]
CAMERAS = [
    "wide 3D preschool music-video shot, gentle side tracking, full bunny visible, slight push toward the action",
    "medium-wide rhythmic tracking shot, gentle left-right parallax, bunny centered, props clearly readable",
    "slightly elevated arc shot that resolves to medium-wide, smooth motion only, bunny and props stay readable",
    "wide hero shot with a very gentle push-in during the final beat, clean celebratory composition",
]


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        print(p.stdout[-8000:])
        raise RuntimeError("Command failed")
    return p.stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)]).strip().splitlines()[-1])


def write_wav(path, samples, rate=44100):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        raw = bytearray()
        for x in samples: raw += int(max(-1.0, min(1.0, x)) * 32767).to_bytes(2, "little", signed=True)
        wf.writeframes(raw)


def tone(buf, start, length, freq, amp, rate=44100):
    a = max(0, int(start * rate)); b = min(len(buf), int((start + length) * rate))
    for i in range(a, b):
        t = i / rate - start
        env = min(1.0, t / 0.015) * max(0.0, (length - t) / max(0.03, length * 0.35))
        v = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(2 * math.pi * 2 * freq * t)
        buf[i] += amp * env * v


def make_music(path):
    rate = 44100; buf = [0.0] * int(TOTAL * rate)
    melody = [523.25, 587.33, 659.25, 698.46, 659.25, 587.33, 523.25, 493.88]
    bass = [261.63, 220.00, 246.94, 196.00]
    for beat_no in range(int(TOTAL / BEAT)):
        t = beat_no * BEAT
        tone(buf, t, 0.20, melody[beat_no % len(melody)], 0.045)
        if beat_no % 4 == 0: tone(buf, t, 0.34, bass[(beat_no // 4) % len(bass)], 0.035)
        if beat_no % 2 == 1: tone(buf, t, 0.09, 1046.50, 0.018)
    write_wav(path, buf, rate)


def make_pop(path, pitch=880):
    rate = 44100; buf = [0.0] * int(0.35 * rate)
    tone(buf, 0, 0.18, pitch, 0.16, rate); tone(buf, 0.06, 0.16, pitch * 1.5, 0.09, rate)
    write_wav(path, buf, rate)


def gemini_plan():
    history = load_history(); old_titles = [x.get("title", "") for x in history[-20:] if isinstance(x, dict)]
    prompt = f"""
You are the showrunner and music director for an ORIGINAL premium Hindi preschool rhyme.
Do not imitate or copy any existing channel, song, lyric, melody, character, branding or distinctive scene.
Use only broad genre principles: repetition, call-and-response, dancing, physical comedy, colorful learning props and a big happy payoff.
CATEGORY: {CATEGORY}
LESSON: {DATA['lesson']}
EXACT ITEMS: {json.dumps(DATA['items'], ensure_ascii=False)}
CHARACTER LOCK: {CHARACTER}
WORLD LOCK: {WORLD}
TEMPO: exactly {BPM} BPM, 4/4 feel.
OLD TITLES TO AVOID: {json.dumps(old_titles, ensure_ascii=False)}
Design four 5-second blocks. Every block must have a clear musical action and visual action on the beat.
Use very short Hindi phrases suitable for ages 2-6. Prefer repetition over explanation.
Every block creates a small payoff; block 4 is the biggest payoff.
Return JSON only with title and four scenes. Each scene needs lyrics, visual_action, camera and beat_action.
Do not put any numbers, letters or words into visual_action; the renderer adds learning labels later.
"""
    client = genai.Client(api_key=GEMINI_KEY); last = None
    for model in [GEMINI_MODEL, GEMINI_FALLBACK]:
        try:
            r = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json"))
            data = json.loads(r.text)
            if len(data.get("scenes", [])) != 4: raise ValueError("Gemini must return exactly four scenes")
            expected = [DATA["items"][:3], DATA["items"][3:6], DATA["items"][6:9], DATA["items"][9:10]]
            for i, s in enumerate(data["scenes"]):
                s["items"] = expected[i]; s["beat_action"] = FIXED_VISUAL_BEATS[i]; s["camera"] = CAMERAS[i]
                if CATEGORY == "numbers": s["lyrics"] = NUMBER_LYRICS[i]
                else: s["lyrics"] = str(s.get("lyrics", "चलो गाएँ, झूमो गाएँ!"))
            data.update({"category": CATEGORY, "bpm": BPM, "format": "Rhyme Engine V2: 4x5s beat-first blocks", "character_lock": CHARACTER, "world_lock": WORLD})
            return data
        except Exception as exc:
            last = exc; print(f"⚠️ Gemini planner {model} failed: {exc}"); time.sleep(1)
    raise RuntimeError(f"Gemini planner failed: {last}")


def pixazo(prompt, index):
    headers = {"Content-Type": "application/json", "Ocp-Apim-Subscription-Key": PIXAZO_KEY}
    payload = {"prompt": prompt, "negative": NEGATIVE, "aspect": "9:16", "num_frames": 121, "frame_rate": 24, "steps": 8, "cfg": 3.0}
    r = requests.post(f"{API_BASE}/ltx-video/v1/text-to-video", headers=headers, json=payload, timeout=90)
    if r.status_code >= 400: raise RuntimeError(f"Pixazo HTTP {r.status_code}: {r.text[:1500]}")
    d = r.json(); rid = d.get("request_id")
    if not rid: raise RuntimeError(f"Pixazo returned no request_id: {d}")
    status_url = d.get("polling_url") or f"{API_BASE}/v2/requests/status/{rid}"
    print(f"🎬 Pixazo V2 block {index+1}/4 request={rid}")
    for n in range(1, 301):
        time.sleep(5); sr = requests.get(status_url, headers={"Ocp-Apim-Subscription-Key": PIXAZO_KEY}, timeout=45); sr.raise_for_status()
        sd = sr.json(); status = str(sd.get("status", "")).upper()
        if n == 1 or n % 12 == 0 or status not in ("PROCESSING", "QUEUED"): print(f"   status={status} ({n*5/60:.1f} min)")
        if status == "COMPLETED":
            media = sd.get("output", {}).get("media_url")
            if isinstance(media, list): return media[0]
            if isinstance(media, str): return media
            raise RuntimeError(f"Pixazo completed without media URL: {sd}")
        if status in ("ERROR", "FAILED", "CANCELLED"): raise RuntimeError(f"Pixazo generation failed: {sd}")
    raise TimeoutError("Pixazo block timed out after 25 minutes")


def video_prompt(scene, index):
    return f"""
PREMIUM 3D PRESCHOOL MUSIC VIDEO. One 5-second performance block inside one continuous 20-second original Hindi children's rhyme.
CHARACTER LOCK — NEVER CHANGE: {CHARACTER}
WORLD LOCK — NEVER CHANGE: {WORLD}
ABSOLUTE: animate only. Generate ZERO text, letters, digits, captions, signs or writing. Never invent a second character.
Learning props are physical {DATA['objects']}; they are props, not characters.
EXACT PROPS FOR THIS BLOCK: {json.dumps(scene['items'], ensure_ascii=False)}.
CHOREOGRAPHY: {FIXED_VISUAL_BEATS[index]}
CAMERA: {CAMERAS[index]}
The bunny MUST physically dance, clap, hop, point, spin or interact with props. No talking-head pose and no slideshow.
Objects visibly react to the beat. Use smooth readable 24fps motion, joyful facial expression, polished children's animation, bright colors, soft studio-quality lighting and strong silhouettes.
Maintain exact bunny identity, outfit, proportions and garden design from every other block.
"""


def download(url, path):
    r = requests.get(url, timeout=180); r.raise_for_status(); path.write_bytes(r.content)
    if path.stat().st_size < 10000: raise RuntimeError("Downloaded video is too small")


def normalize_clip(src, dst):
    run(["ffmpeg", "-y", "-i", str(src), "-vf", f"scale={W}:{H}:flags=lanczos,setsar=1,tpad=stop_mode=clone:stop_duration=5,trim=duration=5,setpts=PTS-STARTPTS", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), "-pix_fmt", "yuv420p", str(dst)])


def concat_video(clips, out):
    listing = WORK / "rhyme_v2_concat.txt"; listing.write_text("\n".join(f"file '{p.resolve()}'" for p in clips), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-t", "20", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), "-pix_fmt", "yuv420p", str(out)])
    d = duration(out)
    if d < 19.95: raise RuntimeError(f"V2 video assembly is too short: {d:.3f}s")


def pcm_wav(path, pcm, rate=24000):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate); wf.writeframes(pcm)


def gemini_tts(text, path):
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = (f"Sing this ORIGINAL Hindi preschool rhyme as a bright playful children's song at approximately {BPM} BPM in 4/4. "
              "Use a simple bouncy melody-like cadence, clear Hindi pronunciation, short rhythmic phrases, smiling energy, "
              "call-and-response feeling, tiny pauses at line breaks, and a strong cheerful ending. Do not narrate, lecture, "
              "read like an audiobook, or sound robotic. Keep every word exactly as supplied.\n\n" + text)
    r = client.models.generate_content(model=GEMINI_TTS_MODEL, contents=prompt, config=types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")))))
    part = r.candidates[0].content.parts[0]; data = part.inline_data.data
    if isinstance(data, str): data = base64.b64decode(data)
    pcm_wav(path, data)


def edge_tts_fallback(text, path):
    """Reliable fallback when Gemini TTS is temporarily unavailable or overloaded."""
    import edge_tts
    print("🔁 FALLBACK TTS: Microsoft Edge hi-IN-SwaraNeural")
    asyncio.run(edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate="-3%", pitch="+2Hz").save(str(path)))


def generate_voice(text, path):
    try:
        gemini_tts(text, path)
        print("🎤 Gemini 3.1 Flash TTS: sing-song mode")
        return "gemini"
    except Exception as exc:
        print(f"⚠️ Gemini TTS unavailable: {exc}")
        edge_tts_fallback(text, path)
        return "edge_fallback"


def fit_voice(src, dst, target=5.0):
    d = max(0.2, duration(src)); ratio = min(2.0, max(0.5, d / max(0.5, target - 0.08)))
    run(["ffmpeg", "-y", "-i", str(src), "-af", f"atempo={ratio:.5f},apad,atrim=0:{target:.3f},loudnorm=I=-17:TP=-2:LRA=8", "-ar", "44100", "-ac", "1", "-c:a", "aac", "-b:a", "128k", str(dst)])


def make_ass(plan, path):
    def ts(x):
        m = int(x // 60); s = x - m * 60; return f"0:{m:02d}:{s:05.2f}"
    lines = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "", "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding", "Style: Beat,Noto Sans Devanagari,78,&H00FFFFFF,&H00FFFFFF,&H0015222D,&HAA000000,1,0,0,0,100,100,0,0,1,5,2,5,40,40,0,1", "Style: Lyric,Noto Sans Devanagari,48,&H00FFFFFF,&H00FFFFFF,&H0015222D,&H99000000,1,0,0,0,100,100,0,0,1,4,1,2,55,55,165,1", "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for i, scene in enumerate(plan["scenes"]):
        base = i * 5.0
        for j, item in enumerate([str(x) for x in scene["items"]]):
            start = base + 0.35 + j * 1.0; end = min(base + 5.0, start + 0.95)
            txt = item.replace("{", "(").replace("}", ")")
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Beat,,0,0,0,,{{\\fscx70\\fscy70\\t(0,160,\\fscx115\\fscy115)\\t(160,260,\\fscx100\\fscy100)}}{txt}")
        lyric = str(scene.get("lyrics", "")).replace("{", "(").replace("}", ")").replace("\n", "\\N")
        lines.append(f"Dialogue: 1,{ts(base)},{ts(base+5)},Lyric,,0,0,0,,{lyric}")
    path.write_text("\n".join(lines), encoding="utf-8")


def mux(video, music, voices, pops, ass, out):
    cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(music)]
    for v in voices: cmd += ["-i", str(v)]
    for p in pops: cmd += ["-i", str(p)]
    filters = ["[1:a]volume=0.075[music]"]; mix = ["[music]"]
    for i in range(4):
        vi = 2 + i; delay = int(i * 5.0 * 1000)
        filters.append(f"[{vi}:a]adelay={delay}|{delay},volume=1.18[v{i}]"); mix.append(f"[v{i}]")
    for i in range(4):
        pi = 6 + i; delay = int((i * 5.0 + 0.35) * 1000)
        filters.append(f"[{pi}:a]adelay={delay}|{delay},volume=0.55[p{i}]"); mix.append(f"[p{i}]")
    filters.append("".join(mix) + f"amix=inputs={len(mix)}:duration=longest:dropout_transition=0,loudnorm=I=-15.5:TP=-1.5:LRA=9[aout]")
    vf = f"subtitles='{ass.as_posix()}':fontsdir=/usr/share/fonts/truetype,setsar=1"
    cmd += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]", "-vf", vf, "-t", "20", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", str(out)]
    run(cmd)
    d = duration(out)
    if d < 19.95: raise RuntimeError(f"Final V2 output is too short: {d:.3f}s")


def main():
    if not GEMINI_KEY or not PIXAZO_KEY: raise RuntimeError("GEMINI_API_KEY and PIXAZO_API_KEY are required")
    WORK.mkdir(exist_ok=True)
    plan = gemini_plan(); META.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_clips = []; clean_clips = []
    for i, scene in enumerate(plan["scenes"]):
        raw = WORK / f"rhyme_v2_raw_{i+1}.mp4"; clean = WORK / f"rhyme_v2_clean_{i+1}.mp4"
        download(pixazo(video_prompt(scene, i), i), raw); normalize_clip(raw, clean); raw_clips.append(raw); clean_clips.append(clean)
    silent = WORK / "rhyme_v2_silent_20s.mp4"; concat_video(clean_clips, silent)
    voices = []; pops = []
    for i, scene in enumerate(plan["scenes"]):
        raw_voice = WORK / f"rhyme_v2_voice_{i+1}.wav"; fitted = WORK / f"rhyme_v2_voice_{i+1}.m4a"
        generate_voice(str(scene["lyrics"]), raw_voice); fit_voice(raw_voice, fitted, 5.0); voices.append(fitted)
        pop = WORK / f"rhyme_v2_pop_{i+1}.wav"; make_pop(pop, [880, 988, 1175, 1319][i]); pops.append(pop)
    music = WORK / "rhyme_v2_music_124bpm.wav"; make_music(music)
    ass = WORK / "rhyme_v2_learning_overlay.ass"; make_ass(plan, ass)
    mux(silent, music, voices, pops, ass, OUT)
    print(f"✅ RHYME ENGINE V2 FINAL: {OUT} | {duration(OUT):.3f}s | {BPM} BPM | 4/4 | 24fps | 9:16")

if __name__ == "__main__": main()
