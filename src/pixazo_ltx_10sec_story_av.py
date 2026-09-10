import asyncio
import os
import time
from pathlib import Path

import requests
import edge_tts

from toon_kids_story import WORK, local_story, load_history
from hf_wan_10sec_story_av_v2 import assemble, mux, make_music, make_sfx, fit_voice, make_ass, sfx_kind

API_KEY = os.getenv("PIXAZO_API_KEY", "").strip()
OUT = Path(os.getenv("PIXAZO_OUTPUT", "toon_pixazo_ltx_10sec_story_av.mp4"))
SLOTS = [3.25, 3.35, 3.40]
API_BASE = "https://gateway.pixazo.ai"


def pixazo_request(prompt, index):
    if not API_KEY:
        raise RuntimeError("PIXAZO_API_KEY is not set")

    # Pixazo's current FREE LTX 2.5 endpoint is /ltx-video/v1/text-to-video.
    # It is asynchronous: submit -> request_id -> poll -> media_url.
    url = f"{API_BASE}/ltx-video/v1/text-to-video"
    headers = {
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": API_KEY,
    }
    # 81 frames at 24fps = 3.375s, close to each 3.2-3.4s timeline slot.
    payload = {
        "prompt": prompt,
        "negative": "blurry, low quality, distorted face, deformed body, extra limbs, bad anatomy, duplicate character, character morphing, face morphing, flicker, jitter, unstable clothing, unstable colors, text, letters, subtitles, logo, watermark",
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

    for _ in range(120):
        time.sleep(5)
        sr = requests.get(
            status_url,
            headers={"Ocp-Apim-Subscription-Key": API_KEY},
            timeout=45,
        )
        if sr.status_code >= 400:
            raise RuntimeError(f"Pixazo status HTTP {sr.status_code}: {sr.text[:1500]}")
        sd = sr.json()
        status = str(sd.get("status", "")).upper()
        print(f"   Pixazo status: {status}")

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

    raise TimeoutError("Pixazo generation timed out after 10 minutes")


def download(url, path):
    print("⬇️ Downloading Pixazo video")
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    path.write_bytes(r.content)
    if path.stat().st_size < 10000:
        raise RuntimeError(f"Downloaded Pixazo file looks invalid: {path}")


def scene_prompt(story, scene):
    return (
        "Premium polished 3D children's cartoon animation for a Hindi kids story. "
        "Use one consistent cute main character for this scene. Do not add text, subtitles, logos or watermarks. "
        f"Main character: {story.get('character', 'cute cartoon animal')}. "
        f"Scene action: {scene.get('visual', '')}. "
        f"Camera: {scene.get('camera', 'gentle cinematic camera movement')}. "
        "Bright colorful family-friendly animated-film look, stable anatomy, smooth natural motion, expressive face, vertical 9:16 social-video composition."
    )


async def tts(text, path):
    await edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate="+10%").save(str(path))


def main():
    WORK.mkdir(exist_ok=True)
    story = local_story(load_history())
    scenes = story.get("scenes", [])[:3]
    if len(scenes) < 3:
        raise RuntimeError("Need at least 3 scenes")
    print(f"📖 {story['title']}")

    clips = []
    for i, scene in enumerate(scenes):
        raw = WORK / f"pixazo_clip_raw_{i}.mp4"
        url = pixazo_request(scene_prompt(story, scene), i)
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
    print(f"✅ Pixazo final video: {OUT}")


if __name__ == "__main__":
    main()
