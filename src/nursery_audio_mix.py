import asyncio
import math
import subprocess
import wave
from pathlib import Path

from hf_wan_10sec_story import WORK, OUT, FINAL_SECONDS, main as video_main

RATE = 48000


def _tone(buf, start, duration, freq, amp=0.1, decay=1.0, harmonics=1):
    a = max(0, int(start * RATE))
    b = min(len(buf), int((start + duration) * RATE))
    for i in range(a, b):
        t = i / RATE - start
        env = min(1.0, t / 0.012) * max(0.0, 1.0 - t / duration) ** decay
        value = math.sin(2 * math.pi * freq * t)
        if harmonics > 1:
            value += 0.35 * math.sin(2 * math.pi * freq * 2 * t)
        buf[i] += amp * value * env


def _kick(buf, start, amp=0.22):
    a = int(start * RATE)
    b = min(len(buf), a + int(0.16 * RATE))
    for i in range(a, b):
        t = (i - a) / RATE
        freq = 125.0 - 70.0 * min(1.0, t / 0.12)
        env = math.exp(-20.0 * t)
        buf[i] += amp * math.sin(2 * math.pi * freq * t) * env


def _clap(buf, start, amp=0.12):
    a = int(start * RATE)
    b = min(len(buf), a + int(0.11 * RATE))
    for i in range(a, b):
        t = (i - a) / RATE
        env = math.exp(-32.0 * t)
        noise = math.sin(2 * math.pi * 1733 * t) + 0.5 * math.sin(2 * math.pi * 2311 * t)
        buf[i] += amp * noise * env * 0.5


def make_music(path):
    total = int(FINAL_SECONDS * RATE)
    buf = [0.0] * total
    # Bright, child-friendly major-key arrangement: C - G - Am - F.
    chords = [
        (0.0, [261.63, 329.63, 392.00]),
        (2.5, [196.00, 246.94, 293.66]),
        (5.0, [220.00, 261.63, 329.63]),
        (7.5, [174.61, 220.00, 261.63]),
    ]
    for start, notes in chords:
        for note in notes:
            _tone(buf, start, 2.25, note, amp=0.045, decay=0.45, harmonics=2)
    melody = [523.25, 587.33, 659.25, 783.99, 659.25, 587.33, 523.25, 659.25,
              698.46, 783.99, 880.00, 783.99, 698.46, 659.25, 587.33, 523.25]
    for i, note in enumerate(melody):
        start = i * 0.625
        _tone(buf, start, 0.48, note, amp=0.095, decay=0.65, harmonics=2)
        _tone(buf, start + 0.01, 0.22, note * 2, amp=0.018, decay=1.0)
    bass = [130.81, 98.00, 110.00, 87.31]
    for bar, note in enumerate(bass):
        start = bar * 2.5
        for beat in range(4):
            _tone(buf, start + beat * 0.625, 0.42, note, amp=0.065, decay=0.7)
    for beat in range(20):
        t = beat * 0.5
        _kick(buf, t, 0.13 if beat % 2 == 0 else 0.09)
        if beat % 2 == 1:
            _clap(buf, t, 0.07)
    # Tiny bell accents make it feel like a nursery musical rather than a sine-wave demo.
    for t, note in [(0.05, 1046.5), (2.55, 1318.5), (5.05, 1568.0), (7.55, 1318.5), (9.25, 1046.5)]:
        _tone(buf, t, 0.55, note, amp=0.07, decay=2.2, harmonics=2)
    peak = max(1e-6, max(abs(x) for x in buf))
    gain = min(1.0, 0.82 / peak)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(int(max(-1.0, min(1.0, x * gain)) * 32767).to_bytes(2, "little", signed=True) for x in buf))


def make_sfx(path):
    total = int(FINAL_SECONDS * RATE)
    buf = [0.0] * total
    # Bunny hops: soft low thump + bright tick, one set per scene.
    for scene_start in (0.15, 3.65, 7.15):
        for hop in range(2):
            t = scene_start + hop * 0.55
            _kick(buf, t, 0.18)
            _tone(buf, t + 0.035, 0.16, 880 + hop * 220, amp=0.11, decay=2.0)
    # Sparkle transitions.
    for base in (2.9, 6.4, 9.15):
        for j, note in enumerate((1046.5, 1318.5, 1568.0)):
            _tone(buf, base + j * 0.08, 0.34, note, amp=0.08, decay=2.4)
    # Short airy whoosh sweeps before scene changes.
    for base in (3.32, 6.82):
        a = int(base * RATE)
        b = min(len(buf), a + int(0.28 * RATE))
        for i in range(a, b):
            t = (i - a) / RATE
            freq = 500 + 1800 * t / 0.28
            env = math.sin(math.pi * t / 0.28) ** 1.5
            buf[i] += 0.055 * math.sin(2 * math.pi * freq * t) * env
    peak = max(1e-6, max(abs(x) for x in buf))
    gain = min(1.0, 0.72 / peak)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(int(max(-1.0, min(1.0, x * gain)) * 32767).to_bytes(2, "little", signed=True) for x in buf))


async def make_voice(text, path):
    import edge_tts
    # Deliberately slower than the previous +12% setting for clear nursery narration.
    await edge_tts.Communicate(
        text=text,
        voice="hi-IN-SwaraNeural",
        rate="-8%",
        pitch="+1Hz",
    ).save(str(path))


def add_rhyme_audio(video, story):
    music = WORK / "nursery_music.wav"
    sfx = WORK / "nursery_sfx.wav"
    voice = WORK / "nursery_rhyme_voice.mp3"
    make_music(music)
    make_sfx(sfx)
    rhyme = story.get("rhyme") or " ".join(scene.get("narration", "") for scene in story.get("scenes", [])[:3])
    if not rhyme.strip():
        raise RuntimeError("Nursery rhyme text is empty; refusing to publish a silent narration track.")
    print("🎵 Creating full nursery soundtrack: music + SFX + Hindi voice...")
    print(f"🗣️ Rhyme: {rhyme}")
    asyncio.run(make_voice(rhyme, voice))
    out = OUT.with_name(OUT.stem + "_av.mp4")
    # Duck music under speech, keep SFX punchy, then normalize the finished mix.
    filter_complex = (
        "[1:a]aresample=48000,volume=0.92[m];"
        "[2:a]aresample=48000,acompressor=threshold=-20dB:ratio=2.2:attack=5:release=120,volume=1.12[v];"
        "[3:a]aresample=48000,volume=0.70[s];"
        "[m][v]sidechaincompress=threshold=0.025:ratio=3.5:attack=15:release=280[duck];"
        "[duck][s][v]amix=inputs=3:duration=longest:dropout_transition=0:weights='1 0.85 1.25',"
        "loudnorm=I=-14:TP=-1.5:LRA=9[aout]"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(video), "-i", str(music), "-i", str(voice), "-i", str(sfx),
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]", "-t", str(FINAL_SECONDS),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(out),
    ]
    subprocess.run(cmd, check=True)
    out.replace(video)


if __name__ == "__main__":
    # Reuse the tested cinematic Wan pipeline, replacing only its weak audio stage.
    import hf_wan_10sec_story as pipeline
    pipeline.add_rhyme_audio = add_rhyme_audio
    pipeline.make_voice = make_voice
    video_main()
