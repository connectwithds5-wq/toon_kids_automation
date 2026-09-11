"""Compatibility wrapper for the proven local Toon Kids renderer.

The original renderer used `d` inside zoompan x/y expressions. In FFmpeg's
zoompan filter the duration variable is named `duration`, while `d` is the
filter option itself. This wrapper monkey-patches only animate_scene so the
existing renderer can run unchanged otherwise.
"""

from pathlib import Path

import toon_kids_story as engine


def animate_scene_fixed(image_path, tts_path, out_path, index):
    """Render one scene with a portable FFmpeg zoompan expression."""
    if index % 4 == 0:
        z = "min(zoom+0.0009,1.10)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif index % 4 == 1:
        z = "min(zoom+0.0007,1.08)"
        x = "(iw-iw/zoom)*on/(duration-1)"
        y = "ih/2-(ih/zoom/2)"
    elif index % 4 == 2:
        z = "min(zoom+0.0008,1.09)"
        x = "(iw-iw/zoom)*(1-on/(duration-1))"
        y = "ih/2-(ih/zoom/2)"
    else:
        z = "1.06"
        x = "iw/2-(iw/zoom/2)"
        y = "(ih-ih/zoom)*(on/(duration-1))"

    vf = (
        "scale=1280:2276:force_original_aspect_ratio=increase,"
        "crop=1280:2276,"
        f"zoompan=z='{z}':x='{x}':y='{y}':"
        f"d={engine.SCENE_SECONDS * engine.FPS}:"
        f"s={engine.WIDTH}x{engine.HEIGHT}:fps={engine.FPS},"
        "format=yuv420p"
    )

    engine.ffmpeg_run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-i", str(tts_path),
        "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
        "-t", str(engine.SCENE_SECONDS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-r", str(engine.FPS), "-pix_fmt", "yuv420p",
        "-af", "apad=pad_dur=8,atrim=0:8,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", str(out_path),
    ])


# Patch only the broken function. All story generation, artwork, TTS,
# history, and output logic remains the original production implementation.
engine.animate_scene = animate_scene_fixed

if __name__ == "__main__":
    engine.main()
