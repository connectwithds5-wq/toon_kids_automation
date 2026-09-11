import os
import subprocess
from pathlib import Path

INPUT = Path(os.getenv("INPUT_VIDEO", "toon_wan_10sec_story_av_v2.mp4"))
OUTPUT = Path(os.getenv("OUTPUT_VIDEO", "toon_wan_10sec_story_4k.mp4"))

# 4K vertical / Shorts-Reels-TikTok canvas: 2160x3840.
# Wan 2.2 generates the motion at a practical resolution; this stage produces
# a clean 4K master without changing duration, FPS, audio, or aspect ratio.


def main():
    if not INPUT.is_file() or INPUT.stat().st_size == 0:
        raise FileNotFoundError(f"Input video not found: {INPUT}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(INPUT),
        "-vf", "scale=2160:3840:flags=lanczos,setsar=1",
        "-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "medium"),
        "-crf", os.getenv("X264_CRF", "16"),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(OUTPUT),
    ]
    print("Creating 4K vertical master (2160x3840)...")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

    probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name:format=duration,size",
        "-of", "default=noprint_wrappers=1",
        str(OUTPUT),
    ]
    subprocess.run(probe, check=True)
    print(f"OK: {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
