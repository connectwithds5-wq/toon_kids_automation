import asyncio
import json
import os
import time
from pathlib import Path

import requests
import edge_tts
from google import genai
from google.genai import types

from toon_kids_story import WORK, choose_topic, load_history
from hf_wan_10sec_story_av_v2 import assemble, mux, make_music, make_sfx, fit_voice, make_ass, sfx_kind

PIXAZO_KEY = os.getenv("PIXAZO_API_KEY", "").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
OUT = Path(os.getenv("PIXAZO_OUTPUT", "toon_pixazo_ltx_10sec_story_av.mp4"))
META = Path(os.getenv("PIXAZO_METADATA", "pixazo_story_metadata.json"))
SLOTS = [3.25, 3.35, 3.40]
API_BASE = "https://gateway.pixazo.ai"


CINEMATIC_BIBLE = """
Premium 3D animated-feature-quality children's cartoon, cute expressive characters,
soft physically believable lighting, rich colorful environment, polished fur/feathers,
cinematic depth of field, clean composition, smooth natural motion.
Keep the SAME main character, face, body proportions, colors and outfit in every scene.
Keep the SAME location and visual world unless the story explicitly requires a small nearby reveal.
Vertical 9:16 composition, subject readable in the center safe area, no text or UI.
Use purposeful camera language, not random zooming. Prefer establishing wides and medium shots;
use close-ups only when an emotion or important object needs emphasis.
"""

NEGATIVE = (
    "blurry, low quality, distorted face, deformed body, extra limbs, bad anatomy, "
    "duplicate character, character morphing, face morphing, flicker, jitter, unstable clothing, "
    "unstable colors, random camera shake, extreme unwanted zoom, fisheye distortion, "
    "cropped head, cropped ears, subject out of frame, text, letters, subtitles, logo, watermark, "
    "horror, scary, violence, dark disturbing mood"
)


def gemini_story():
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    history = load_history()
    old_titles = []
    for item in history[-30:]:
        if isinstance(item, dict) and item.get("title"):
            old_titles.append(item["title"])
        elif isinstance(item, str):
            old_titles.append(item[:100])

    topic = choose_topic(history)
    prompt = f"""
You are a senior Hindi children's YouTube storyteller AND cinematic animation director.
Create one original story designed specifically for a 10-second vertical 9:16 AI video test.
Topic seed: {topic}
Avoid repeating these previous titles: {json.dumps(old_titles, ensure_ascii=False)}

The final video has EXACTLY 3 scenes, about 3.3 seconds each.
The story must have a clear mini arc: HOOK -> DISCOVERY/ACTION -> PAYOFF/EMOTIONAL END.
Use one main character consistently. The visual action must be physically simple enough for an AI video model.

CAMERA DIRECTION IS CRITICAL. For each scene explicitly choose a cinematic shot such as:
- Scene 1: wide establishing shot / high-angle or gentle aerial reveal that clearly shows the world.
- Scene 2: medium tracking shot, over-the-shoulder, low-angle or side dolly following the action.
- Scene 3: cinematic medium-to-close emotional payoff or wide hero reveal.
Do NOT make every scene a face close-up. Do NOT use generic 'zoom in'.
Include camera movement, framing, lens feel, subject motion, foreground/background depth, and lighting.

Return ONLY valid JSON with this schema:
{{
  "title": "short catchy Hindi title",
  "topic": "one-line Hindi story premise",
  "moral": "short positive lesson",
  "character": "fixed detailed character appearance including colors and outfit",
  "world": "fixed detailed location/environment",
  "scenes": [
    {{
      "narration": "12-18 simple Hindi words",
      "visual": "specific physical action, environment and emotion",
      "camera": "specific cinematic shot + camera movement + framing",
      "lighting": "specific cinematic lighting",
      "transition": "how this scene naturally leads into the next"
    }}
  ]
}}

Rules:
- Exactly 3 scenes.
- Preschool-friendly, wholesome, funny/warm, visually beautiful.
- Scene 1 must grab attention immediately without a close-up-only composition.
- Scene 2 must visibly advance the story.
- Scene 3 must deliver a satisfying cute payoff and moral feeling.
- Same character, outfit, colors and world across all 3 scenes.
- Avoid crowds and complicated interactions; maximum 2 visible characters at once.
- No written words, signs, captions, logos or watermarks inside the generated video.
"""

    last_error = None
    client = genai.Client(api_key=GEMINI_KEY)
    for model in [GEMINI_MODEL, GEMINI_FALLBACK]:
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
            if len(scenes) != 3:
                raise ValueError(f"Gemini returned {len(scenes)} scenes instead of 3")
            data["character"] = str(data.get("character", "cute cartoon animal"))
            data["world"] = str(data.get("world", "bright magical forest"))
            data["moral"] = str(data.get("moral", "मिल-जुलकर मदद करना सबसे अच्छा है।"))
            for scene in scenes:
                scene.setdefault("narration", "")
                scene.setdefault("visual", "")
                scene.setdefault("camera", "cinematic medium tracking shot")
                scene.setdefault("lighting", "soft warm cinematic light")
                scene.setdefault("transition", "natural continuous movement")
            print(f"🧠 Gemini story generated with {model}: {data['title']}")
            return data
        except Exception as exc:
            last_error = exc
            print(f"⚠️ Gemini model {model} failed: {exc}")
            time.sleep(1)
    raise RuntimeError(f"Gemini story generation failed: {last_error}")


def pixazo_request(prompt, index):
    if not PIXAZO_KEY:
        raise RuntimeError("PIXAZO_API_KEY is not set")

    url = f"{API_BASE}/ltx-video/v1/text-to-video"
    headers = {
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": PIXAZO_KEY,
    }
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

    max_polls = 300
    for poll_no in range(1, max_polls + 1):
        time.sleep(5)
        sr = requests.get(
            status_url,
            headers={"Ocp-Apim-Subscription-Key": PIXAZO_KEY},
            timeout=45,
        )
        if sr.status_code >= 400:
            raise RuntimeError(f"Pixazo status HTTP {sr.status_code}: {sr.text[:1500]}")
        sd = sr.json()
        status = str(sd.get("status", "")).upper()
        elapsed_min = (poll_no * 5) / 60
        if poll_no == 1 or poll_no % 12 == 0 or status != "PROCESSING":
            print(f"   Pixazo status: {status} ({elapsed_min:.1f} min)")

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


def scene_prompt(story, scene, index):
    shot_plan = [
        "ESTABLISHING SHOT: start with a beautiful wide/high-angle view of the environment, then a gentle cinematic crane/drone-like reveal toward the character. Show foreground depth, full body and surroundings. Do not start with a face close-up.",
        "ACTION SHOT: use a smooth medium side-tracking/dolly shot following the character's physical action. Keep the character fully readable, with layered foreground and background parallax. Brief over-the-shoulder feeling is okay, but avoid extreme close-up.",
        "PAYOFF SHOT: use a cinematic medium shot that can gently push toward the emotional moment, then finish with a small hero reveal/wider composition. Keep both character and environment visible and stable."
    ][index]
    return (
        f"{CINEMATIC_BIBLE}\n"
        f"FIXED CHARACTER: {story.get('character', '')}\n"
        f"FIXED WORLD: {story.get('world', '')}\n"
        f"STORY TITLE: {story.get('title', '')}\n"
        f"SCENE {index + 1} ACTION: {scene.get('visual', '')}\n"
        f"CAMERA DIRECTOR NOTE: {scene.get('camera', '')}\n"
        f"SHOT PLAN: {shot_plan}\n"
        f"LIGHTING: {scene.get('lighting', '')}\n"
        f"TRANSITION CONTINUITY: {scene.get('transition', '')}\n"
        "Motion should be smooth, deliberate and physically plausible. Preserve character identity throughout the shot. "
        "No text, subtitles, logos or watermarks."
    )


async def tts(text, path):
    await edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate="+10%").save(str(path))


def main():
    WORK.mkdir(exist_ok=True)
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is required for the cinematic Gemini pipeline")
    if not PIXAZO_KEY:
        raise RuntimeError("PIXAZO_API_KEY secret is required")

    story = gemini_story()
    scenes = story["scenes"]
    print(f"📖 {story['title']}")
    print(f"💡 Moral: {story['moral']}")

    META.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")

    clips = []
    for i, scene in enumerate(scenes):
        raw = WORK / f"pixazo_clip_raw_{i}.mp4"
        url = pixazo_request(scene_prompt(story, scene, i), i)
        download(url, raw)
        clips.append(raw)

    voices, sfxs = [], []
    for i, scene in enumerate(scenes):
        raw_voice = WORK / f"pixazo_voice_raw_{i}.mp3"
        voice = WORK / f"pixazo_voice_{i}.m4a"
        fx = WORK / f"pixazo_sfx_{i}.wav"
        asyncio.run(tts(scene.get("narration", ""), raw_voice))
        fit_voice(raw_voice, voice, SLOTS[i])
        make_sfx(fx, sfx_kind(scene))
        voices.append(voice)
        sfxs.append(fx)

    video = WORK / "pixazo_video.mp4"
    assemble(clips, video)
    music = WORK / "pixazo_music.wav"
    make_music(music)
    ass = WORK / "pixazo_subtitles.ass"
    make_ass(scenes, ass)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    mux(video, music, voices, sfxs, ass, OUT)
    print(f"✅ Pixazo + Gemini final video: {OUT}")
    print(f"📝 Story metadata: {META}")


if __name__ == "__main__":
    main()
