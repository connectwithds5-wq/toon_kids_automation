import asyncio
import os
import shutil
import subprocess
import wave
from pathlib import Path

import edge_tts
from gradio_client import Client, handle_file

from toon_kids_story import WORK, local_story, load_history, scene_image

SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_10sec_story_av.mp4"))
CLIP_SECONDS = 10.0 / 3.0
FINAL_SECONDS = 10.0
FPS = 16
W, H = 1080, 1920
SCENES = 3
TTS_RATE = os.getenv("TTS_RATE", "-6%")


def extract_video_path(result):
    if isinstance(result, dict):
        for key in ("video", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"No video path in HF result: {result!r}")
    if isinstance(result, (tuple, list)):
        for item in result:
            if isinstance(item, str) and (item.endswith((".mp4", ".webm", ".mov", ".mkv")) or Path(item).is_file()):
                return item
            try:
                return extract_video_path(item)
            except RuntimeError:
                pass
        raise RuntimeError(f"No video path in HF result: {result!r}")
    if isinstance(result, str) and result:
        return result
    raise RuntimeError(f"Unsupported HF result: {result!r}")


def make_clip(client, story, scene, index):
    image_path = WORK / f"av_scene_{index + 1}.png"
    clip_path = WORK / f"av_scene_{index + 1}.mp4"
    scene_image(story, scene, index, image_path)

    prompt = (
        "High quality preschool 3D cartoon animation. Preserve the input character EXACTLY: "
        "same species, face, eyes, body proportions, skin color, clothing, hat, scarf and colors. "
        "Do not redesign or add accessories. Keep the character centered and recognizable. "
        f"Character reference: {story.get('character', 'cute cartoon animal')}. "
        f"Action: {scene.get('visual', '')}. Camera: {scene.get('camera', 'very gentle cinematic push in')}. "
        "Slow gentle movement, natural child-friendly motion, stable anatomy, stable face, "
        "stable clothing, smooth motion, bright colorful children's movie style. "
        "Avoid fast motion, sudden pose changes, morphing and camera shake. "
        "No text, letters, captions, subtitles, logos, watermarks or UI elements."
    )[:950]
    negative = (
        "text, letters, words, subtitles, caption, logo, watermark, badge, label, UI, "
        "blurry, low quality, out of focus, distorted face, deformed body, extra limbs, "
        "missing limbs, bad anatomy, duplicate character, character morphing, face morphing, "
        "identity change, clothing change, hat change, scarf change, color change, flicker, jitter, "
        "frame tearing, camera shake, rapid motion, fast movement, object duplication, artifact"
    )

    print(f"[Scene {index + 1}/{SCENES}] Wan 2.2 {CLIP_SECONDS:.3f}s, slow-motion prompt")
    result = client.predict(
        handle_file(str(image_path)), prompt, 6, negative, CLIP_SECONDS,
        1.0, 1.0, 5000 + index, False, api_name="/generate_video"
    )
    source = Path(extract_video_path(result))
    if not source.is_file():
        raise FileNotFoundError(f"HF video does not exist: {source}")
    shutil.copy2(source, clip_path)
    return clip_path


def write_wav(path, samples, rate=44100):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        raw = bytearray()
        for value in samples:
            value = max(-1.0, min(1.0, value))
            raw += int(value * 32767).to_bytes(2, "little", signed=True)
        wf.writeframes(raw)


def make_music(path, seconds=10.0, rate=44100):
    """Original soft kids music bed with gentle arpeggio and bell-like melody."""
    import math
    total = int(seconds * rate)
    chords = [(261.63, 329.63, 392.00), (220.00, 277.18, 329.63),
              (246.94, 311.13, 369.99), (196.00, 246.94, 293.66)]
    melody = [523.25, 587.33, 659.25, 783.99, 659.25, 587.33, 523.25, 493.88]
    out = []
    for i in range(total):
        t = i / rate
        chord = chords[int(t / 2.5) % len(chords)]
        pad = sum(math.sin(2 * math.pi * f * t) for f in chord) / 3.0
        beat_phase = t % 0.5
        pulse = math.sin(2 * math.pi * 90 * beat_phase) * 0.025 * max(0.0, 1.0 - beat_phase / 0.16)
        mt = t % 2.0
        note = melody[int(mt / 0.25) % len(melody)]
        note_phase = mt % 0.25
        bell_env = math.exp(-8.0 * note_phase)
        bell = (math.sin(2 * math.pi * note * t) + 0.25 * math.sin(2 * math.pi * note * 2 * t)) * 0.055 * bell_env
        fade = min(1.0, t / 0.5, (seconds - t) / 0.8)
        out.append((0.105 * pad + pulse + bell) * max(0.0, fade))
    write_wav(path, out, rate)


def make_sfx(path, kind):
    import math
    rate = 44100
    duration = {"chime": 0.50, "whoosh": 0.42, "sparkle": 0.40, "pop": 0.20}.get(kind, 0.30)
    count = int(duration * rate)
    samples = []
    for i in range(count):
        t = i / rate
        if kind == "whoosh":
            phase = 2 * math.pi * (120 * t + 700 * t * t)
            value = math.sin(phase) * (0.12 + 0.08 * math.sin(2 * math.pi * 7 * t))
        elif kind == "sparkle":
            value = (math.sin(2 * math.pi * 1320 * t) + 0.45 * math.sin(2 * math.pi * 1980 * t)) * 0.10
        elif kind == "chime":
            value = (math.sin(2 * math.pi * 880 * t) + 0.35 * math.sin(2 * math.pi * 1320 * t)) * 0.13
        else:
            value = math.sin(2 * math.pi * (220 + 420 * t) * t) * 0.16
        env = min(1.0, t / 0.015, (duration - t) / 0.10)
        samples.append(value * max(0.0, env))
    write_wav(path, samples, rate)


def sfx_kind(scene):
    text = f"{scene.get('visual', '')} {scene.get('narration', '')}"
    if any(x in text for x in ("चमक", "रोशनी", "खुशी", "सरप्राइज")):
        return "sparkle"
    if any(x in text for x in ("खुल", "दरवाजा", "चाबी")):
        return "chime"
    if any(x in text for x in ("दौड़", "ऊपर", "उड़", "पतंग")):
        return "whoosh"
    return "pop"


async def tts(text, path):
    await edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate=TTS_RATE).save(str(path))


def make_tts_sync(text, path):
    asyncio.run(tts(text, path))


def media_duration(path):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)
    ], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def fit_voice(path, target):
    """Return an audio filter that fits narration inside one scene without making it sound unnaturally fast."""
    duration = media_duration(path)
    ratio = duration / target
    if ratio <= 1.0:
        return "anull"
    # atempo supports 0.5..2.0; slow the voice if it is too long, capped at 0.82x.
    speed = max(0.82, 1.0 / ratio)
    return f"atempo={speed:.4f}"


def concat_video(clips, path):
    concat_file = WORK / "av_concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clips), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-an", "-t", str(FINAL_SECONDS), "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart", str(path)
    ], check=True)


def mux_audio_video(video_path, music, narrations, sfxs, subtitles, path):
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(music)]
    for n, s in zip(narrations, sfxs):
        cmd += ["-i", str(n), "-i", str(s)]

    filters = ["[1:a]volume=0.11[music]"]
    mix_inputs = ["[music]"]
    for i in range(SCENES):
        nidx = 2 + i * 2
        sidx = nidx + 1
        delay = int(round(i * CLIP_SECONDS * 1000))
        voice_filter = fit_voice(narrations[i], CLIP_SECONDS)
        filters.append(f"[{nidx}:a]{voice_filter},adelay={delay}|{delay},volume=1.0[n{i}]")
        filters.append(f"[{sidx}:a]adelay={delay}|{delay},volume=0.42[s{i}]")
        mix_inputs += [f"[n{i}]", f"[s{i}]"]

    filters.append(
        "".join(mix_inputs) +
        f"amix=inputs={len(mix_inputs)}:duration=longest:dropout_transition=0:normalize=0," 
        "loudnorm=I=-16:TP=-1.5:LRA=9[aout]"
    )

    subtitle_filter = subtitles.as_posix().replace("\\", "/").replace("'", "\\'")
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "0:v:0", "-map", "[aout]",
        "-vf", f"scale={W}:{H}:flags=lanczos,subtitles='{subtitle_filter}'",
        "-t", str(FINAL_SECONDS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-movflags", "+faststart", str(path)
    ]
    subprocess.run(cmd, check=True)


def make_ass(scenes, narration_files, path):
    def esc(s):
        return str(s).replace("{", "(").replace("}", ")").replace("\\", "\\\\")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Kids,Noto Sans Devanagari,58,&H00FFFFFF,&H00FFFFFF,&H001B263B,&H90000000,1,0,0,0,100,100,0,0,1,5,2,2,60,60,165,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    for i, (scene, narration) in enumerate(zip(scenes, narration_files)):
        start = i * CLIP_SECONDS
        voice_dur = min(media_duration(narration), CLIP_SECONDS)
        end = min(start + max(voice_dur + 0.08, 0.35), FINAL_SECONDS)
        def ts(sec):
            m = int(sec // 60); s = sec - m * 60
            return f"{m}:{s:04.1f}"
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Kids,,0,0,0,,{esc(scene.get('narration',''))}")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    WORK.mkdir(exist_ok=True)
    story = local_story(load_history())
    scenes = story.get("scenes", [])[:SCENES]
    if len(scenes) < SCENES:
        raise RuntimeError(f"The selected story must contain at least {SCENES} scenes.")

    print(f"Story: {story['title']}")
    print(f"Pipeline: {SCENES} Wan clips + slower Hindi narration ({TTS_RATE}) + music + SFX + timed subtitles")
    client = Client(SPACE, token=HF_TOKEN)
    clips = [make_clip(client, story, scene, i) for i, scene in enumerate(scenes)]

    video = WORK / "av_story_video.mp4"
    concat_video(clips, video)

    music = WORK / "kids_music_original.wav"
    make_music(music, FINAL_SECONDS)
    narrations, sfxs = [], []
    for i, scene in enumerate(scenes):
        n = WORK / f"av_narration_{i+1}.mp3"
        s = WORK / f"av_sfx_{i+1}.wav"
        print(f"Audio scene {i + 1}: Hindi voice + {sfx_kind(scene)} SFX")
        make_tts_sync(scene.get("narration", ""), n)
        make_sfx(s, sfx_kind(scene))
        narrations.append(n)
        sfxs.append(s)

    ass = WORK / "av_subtitles.ass"
    make_ass(scenes, narrations, ass)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    mux_audio_video(video, music, narrations, sfxs, ass, OUT)

    subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
        "-of", "default=noprint_wrappers=1", str(OUT)
    ], check=True)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
