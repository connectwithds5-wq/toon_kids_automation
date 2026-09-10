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
CLIP_SECONDS = 3.5
FINAL_SECONDS = 10.0
FPS = 16
W, H = 1080, 1920


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
        "High quality 3D cartoon children's animation. Keep the EXACT same main character "
        "design, colors, clothes, face and proportions as the input image. "
        f"Character: {story.get('character', 'cute cartoon animal')}. "
        f"Scene action: {scene.get('visual', '')}. "
        f"Camera: {scene.get('camera', 'gentle cinematic movement')}. "
        "Cute expressive movement, natural body motion, stable face, stable anatomy, "
        "smooth cinematic animation, bright colorful children's movie look, clean background, "
        "no text, no letters, no subtitles, no logo, no watermark."
    )[:900]
    negative = (
        "blurry, low quality, out of focus, distorted face, deformed body, extra limbs, "
        "missing limbs, bad anatomy, duplicate character, character morphing, face morphing, "
        "flicker, jitter, frame tearing, unstable clothing, unstable colors, text, letters, "
        "subtitles, logo, watermark, rectangle artifact, gray frame, noisy image"
    )

    print(f"[Scene {index + 1}/3] Wan 2.2 {CLIP_SECONDS}s")
    result = client.predict(
        handle_file(str(image_path)), prompt, 6, negative, CLIP_SECONDS,
        1.0, 1.0, 2000 + index, False, api_name="/generate_video"
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
    """Tiny original, royalty-free children's bed: soft chords + melody + pulse."""
    import math
    total = int(seconds * rate)
    notes = [261.63, 329.63, 392.00, 523.25, 392.00, 329.63, 293.66, 349.23]
    chords = [(261.63, 329.63, 392.00), (220.00, 277.18, 329.63),
              (246.94, 311.13, 369.99), (196.00, 246.94, 293.66)]
    out = []
    for i in range(total):
        t = i / rate
        chord = chords[int(t / 2.5) % len(chords)]
        pad = sum(math.sin(2 * math.pi * f * t) for f in chord) / 3.0
        beat = math.sin(2 * math.pi * 2.0 * t) * (0.08 if (t % 0.5) < 0.08 else 0.0)
        melody_t = t % 4.0
        n = notes[int(melody_t / 0.5) % len(notes)]
        env = max(0.0, 1.0 - ((melody_t % 0.5) / 0.5)) ** 2
        melody = math.sin(2 * math.pi * n * t) * 0.12 * env
        fade = min(1.0, t / 0.4, (seconds - t) / 0.6)
        out.append((0.16 * pad + beat + melody) * max(0.0, fade))
    write_wav(path, out, rate)


def tone(duration, freq, path, volume=0.28, rate=44100, sweep=0.0):
    import math
    count = int(duration * rate)
    samples = []
    for i in range(count):
        t = i / rate
        f = freq + sweep * t
        env = min(1.0, t / 0.02, (duration - t) / 0.08)
        samples.append(math.sin(2 * math.pi * f * t) * volume * max(0.0, env))
    write_wav(path, samples, rate)


def make_sfx(path, kind):
    if kind == "chime":
        tone(0.55, 880, path, 0.30, sweep=240)
    elif kind == "whoosh":
        tone(0.45, 180, path, 0.20, sweep=900)
    elif kind == "sparkle":
        tone(0.35, 1320, path, 0.22, sweep=700)
    elif kind == "pop":
        tone(0.22, 260, path, 0.30, sweep=500)
    else:
        tone(0.30, 440, path, 0.18)


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
    await edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate="+6%").save(str(path))


def make_tts_sync(text, path):
    asyncio.run(tts(text, path))


def concat_video(clips, path):
    concat_file = WORK / "av_concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clips), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-an", "-t", str(FINAL_SECONDS), "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)
    ], check=True)


def mux_audio_video(video_path, music, narrations, sfxs, subtitles, path):
    # Inputs: video, music, then narration/sfx pairs. Delays are scene-relative.
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(music)]
    for n, s in zip(narrations, sfxs):
        cmd += ["-i", str(n), "-i", str(s)]

    filters = ["[1:a]volume=0.16[music]"]
    mix_inputs = ["[music]"]
    for i in range(3):
        nidx = 2 + i * 2
        sidx = nidx + 1
        delay = int(i * 3.3 * 1000)
        filters.append(f"[{nidx}:a]adelay={delay}|{delay},volume=1.25[n{i}]")
        filters.append(f"[{sidx}:a]adelay={delay}|{delay},volume=0.65[s{i}]")
        mix_inputs += [f"[n{i}]", f"[s{i}]"]
    filters.append("".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=longest:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=11[aout]")

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "0:v:0", "-map", "[aout]",
        "-vf", f"scale={W}:{H}:flags=lanczos,subtitles='{subtitles.as_posix()}'",
        "-t", str(FINAL_SECONDS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-ar", "44100", "-movflags", "+faststart", str(path)
    ]
    subprocess.run(cmd, check=True)


def make_ass(story, scenes, path):
    def esc(s):
        return str(s).replace("{", "(").replace("}", ")")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Kids,Noto Sans Devanagari,58,&H00FFFFFF,&H00FFFFFF,&H001B263B,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,60,60,170,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    for i, scene in enumerate(scenes):
        start = i * 3.3
        end = min(start + 3.3, FINAL_SECONDS)
        def ts(sec):
            m = int(sec // 60); s = sec - m * 60
            return f"{m}:{s:04.1f}"
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Kids,,0,0,0,,{esc(scene.get('narration',''))}")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    WORK.mkdir(exist_ok=True)
    story = local_story(load_history())
    scenes = story.get("scenes", [])[:3]
    if len(scenes) < 3:
        raise RuntimeError("The selected story must contain at least 3 scenes.")

    print(f"Story: {story['title']}")
    print("Pipeline: 3 Wan clips + Hindi narration + original music + scene SFX + Hindi subtitles")
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
        narrations.append(n); sfxs.append(s)

    ass = WORK / "av_subtitles.ass"
    make_ass(story, scenes, ass)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    mux_audio_video(video, music, narrations, sfxs, ass, OUT)

    subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
        "-of", "default=noprint_wrappers=1", str(OUT)
    ], check=True)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
