import asyncio
import math
import os
import shutil
import subprocess
import wave
from pathlib import Path

from hf_wan_10sec_story import WORK, OUT, FINAL_SECONDS, main as video_main

RATE = 48000
AI_MUSIC_ENABLED = os.getenv("AI_MUSIC_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
AI_MUSIC_SPACE = os.getenv("AI_MUSIC_SPACE", "ACloudCenter/ACE-Music-Generator")
AI_MUSIC_DURATION = float(os.getenv("AI_MUSIC_DURATION", "12"))


def _tone(buf, start, duration, freq, amp=0.1, decay=1.0, harmonics=1):
    a = max(0, int(start * RATE))
    b = min(len(buf), int((start + duration) * RATE))
    for i in range(a, b):
        t = i / RATE - start
        env = min(1.0, t / 0.008) * max(0.0, 1.0 - t / duration) ** decay
        value = math.sin(2 * math.pi * freq * t)
        if harmonics >= 2:
            value += 0.28 * math.sin(2 * math.pi * freq * 2 * t)
        if harmonics >= 3:
            value += 0.12 * math.sin(2 * math.pi * freq * 3 * t)
        buf[i] += amp * value * env


def _pluck(buf, start, duration, freq, amp=0.12):
    a = max(0, int(start * RATE))
    b = min(len(buf), int((start + duration) * RATE))
    for i in range(a, b):
        t = i / RATE - start
        env = math.exp(-4.8 * t / duration) * min(1.0, t / 0.006)
        v = math.sin(2 * math.pi * freq * t)
        v += 0.38 * math.sin(2 * math.pi * freq * 2 * t)
        v += 0.16 * math.sin(2 * math.pi * freq * 3 * t)
        buf[i] += amp * v * env


def _kick(buf, start, amp=0.18):
    a = int(start * RATE)
    b = min(len(buf), a + int(0.18 * RATE))
    for i in range(a, b):
        t = (i - a) / RATE
        freq = 145.0 - 85.0 * min(1.0, t / 0.12)
        env = math.exp(-18.0 * t)
        buf[i] += amp * math.sin(2 * math.pi * freq * t) * env


def _hat(buf, start, amp=0.035):
    a = int(start * RATE)
    b = min(len(buf), a + int(0.055 * RATE))
    for i in range(a, b):
        t = (i - a) / RATE
        env = math.exp(-65.0 * t)
        noise = (math.sin(2 * math.pi * 3711 * t) + math.sin(2 * math.pi * 5217 * t) + math.sin(2 * math.pi * 7311 * t)) / 3
        buf[i] += amp * noise * env


def _clap(buf, start, amp=0.06):
    _hat(buf, start, amp)
    _hat(buf, start + 0.018, amp * 0.65)


def make_music(path):
    """Offline fallback nursery-pop backing track."""
    total = int(FINAL_SECONDS * RATE)
    buf = [0.0] * total
    chords = [
        (0.0, (261.63, 329.63, 392.00)),
        (2.5, (196.00, 246.94, 293.66)),
        (5.0, (220.00, 261.63, 329.63)),
        (7.5, (174.61, 220.00, 261.63)),
    ]
    for start, notes in chords:
        for note in notes:
            _tone(buf, start, 2.42, note, amp=0.035, decay=0.22, harmonics=3)
            _tone(buf, start + 0.02, 2.20, note * 2, amp=0.012, decay=0.35, harmonics=2)
    bass = [130.81, 98.00, 110.00, 87.31]
    for bar, note in enumerate(bass):
        base = bar * 2.5
        for beat in range(4):
            _tone(buf, base + beat * 0.625, 0.40, note, amp=0.075, decay=0.75)
    melody = [523.25, 587.33, 659.25, 783.99, 659.25, 587.33, 523.25, 659.25, 698.46, 783.99, 880.00, 783.99, 698.46, 659.25, 587.33, 659.25]
    for i, note in enumerate(melody):
        start = i * 0.625
        _pluck(buf, start, 0.52, note, amp=0.105)
        _tone(buf, start + 0.01, 0.28, note * 2, amp=0.014, decay=1.8, harmonics=2)
    for start, note in [(1.56, 783.99), (3.43, 587.33), (5.93, 783.99), (7.81, 659.25), (9.18, 783.99)]:
        _pluck(buf, start, 0.30, note, amp=0.055)
    for beat in range(20):
        t = beat * 0.5
        _kick(buf, t, 0.15 if beat % 2 == 0 else 0.10)
        if beat % 2 == 1:
            _clap(buf, t, 0.075)
        _hat(buf, t + 0.25, 0.028)
    for base, notes in [(2.90, (1046.5, 1318.5, 1568.0)), (6.40, (1174.7, 1480.0, 1760.0)), (9.15, (1046.5, 1318.5, 1568.0))]:
        for j, note in enumerate(notes):
            _tone(buf, base + j * 0.075, 0.48, note, amp=0.075, decay=2.6, harmonics=2)
    for note in (523.25, 659.25, 783.99):
        _pluck(buf, 9.35, 0.58, note, amp=0.055)
    peak = max(1e-6, max(abs(x) for x in buf))
    gain = min(1.0, 0.78 / peak)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(int(max(-1.0, min(1.0, x * gain)) * 32767).to_bytes(2, "little", signed=True) for x in buf))


def make_sfx(path):
    total = int(FINAL_SECONDS * RATE)
    buf = [0.0] * total
    for scene_start in (0.15, 3.65, 7.15):
        for hop in range(2):
            t = scene_start + hop * 0.55
            _kick(buf, t, 0.20)
            _tone(buf, t + 0.035, 0.16, 880 + hop * 220, amp=0.12, decay=2.0)
    for base in (2.9, 6.4, 9.15):
        for j, note in enumerate((1046.5, 1318.5, 1568.0)):
            _tone(buf, base + j * 0.08, 0.34, note, amp=0.09, decay=2.4)
    for base in (3.32, 6.82):
        a = int(base * RATE)
        b = min(len(buf), a + int(0.28 * RATE))
        for i in range(a, b):
            t = (i - a) / RATE
            freq = 500 + 1800 * t / 0.28
            env = math.sin(math.pi * t / 0.28) ** 1.5
            buf[i] += 0.06 * math.sin(2 * math.pi * freq * t) * env
    peak = max(1e-6, max(abs(x) for x in buf))
    gain = min(1.0, 0.70 / peak)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(int(max(-1.0, min(1.0, x * gain)) * 32767).to_bytes(2, "little", signed=True) for x in buf))


async def make_voice(text, path):
    import edge_tts
    await edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate="-8%", pitch="+1Hz").save(str(path))


def generate_ai_rhyme(rhyme, path):
    """Generate a sung nursery rhyme through a free Hugging Face ACE-Step Space."""
    if not AI_MUSIC_ENABLED:
        return False
    try:
        from gradio_client import Client
        token = os.getenv("HF_TOKEN") or None
        print(f"🎼 AI music: connecting to free ACE-Step Space {AI_MUSIC_SPACE}...")
        client = Client(AI_MUSIC_SPACE, token=token)
        tags = (
            "Indian Hindi nursery rhyme, preschool children's song, joyful bright major key, "
            "catchy sing-along melody, playful child-friendly vocal, clear Hindi pronunciation, "
            "ukulele, toy piano, marimba, glockenspiel, hand claps, light kick and percussion, "
            "warm bass, magical bells, cute cartoon energy, simple memorable hook, upbeat 118 bpm, "
            "clean modern kids YouTube production, no rap, no spoken narration"
        )
        result = client.predict(
            AI_MUSIC_DURATION,
            tags,
            rhyme,
            60,
            15.0,
            api_name="/generate",
        )
        source = result[0] if isinstance(result, (tuple, list)) else result
        if not source:
            raise RuntimeError("ACE-Step returned an empty audio result")
        source_path = Path(str(source))
        if not source_path.exists():
            raise RuntimeError(f"ACE-Step returned a missing audio file: {source_path}")
        shutil.copy2(source_path, path)
        print(f"✅ AI sung rhyme created: {path}")
        return True
    except Exception as exc:
        print(f"⚠️ AI music unavailable; using local fallback: {exc}")
        return False


def add_rhyme_audio(video, story):
    music = WORK / "nursery_music.wav"
    sfx = WORK / "nursery_sfx.wav"
    voice = WORK / "nursery_rhyme_voice.mp3"
    ai_music = WORK / "nursery_ai_rhyme.mp3"
    rhyme = story.get("rhyme") or " ".join(scene.get("narration", "") for scene in story.get("scenes", [])[:3])
    if not rhyme.strip():
        raise RuntimeError("Nursery rhyme text is empty; refusing to publish a silent narration track.")

    ai_ok = generate_ai_rhyme(rhyme, ai_music)
    make_sfx(sfx)

    if ai_ok:
        print("🎵 Using AI-generated sung rhyme as the main soundtrack.")
        audio_inputs = [str(ai_music), str(sfx)]
        filter_complex = (
            "[1:a]aresample=48000,volume=0.92[m];"
            "[2:a]aresample=48000,volume=0.52[s];"
            "[m][s]amix=inputs=2:duration=longest:dropout_transition=0:weights='1 0.45',"
            "loudnorm=I=-14:TP=-1.5:LRA=9[aout]"
        )
    else:
        make_music(music)
        asyncio.run(make_voice(rhyme, voice))
        print("🎵 Using local fallback: music + Hindi voice + SFX.")
        audio_inputs = [str(music), str(voice), str(sfx)]
        filter_complex = (
            "[1:a]aresample=48000,volume=0.78[m];"
            "[2:a]aresample=48000,acompressor=threshold=-20dB:ratio=2.2:attack=5:release=120,volume=1.18[v];"
            "[3:a]aresample=48000,volume=0.82[s];"
            "[m][v]sidechaincompress=threshold=0.025:ratio=3.5:attack=15:release=280[duck];"
            "[duck][s][v]amix=inputs=3:duration=longest:dropout_transition=0:weights='1 0.9 1.3',"
            "loudnorm=I=-14:TP=-1.5:LRA=9[aout]"
        )

    out = OUT.with_name(OUT.stem + "_av.mp4")
    cmd = ["ffmpeg", "-y", "-i", str(video)]
    for audio in audio_inputs:
        cmd += ["-i", audio]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]", "-t", str(FINAL_SECONDS),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(out),
    ]
    subprocess.run(cmd, check=True)
    out.replace(video)


if __name__ == "__main__":
    import hf_wan_10sec_story as pipeline
    pipeline.add_rhyme_audio = add_rhyme_audio
    pipeline.make_voice = make_voice
    video_main()
