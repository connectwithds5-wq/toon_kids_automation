import subprocess
import sys
from pathlib import Path

# High-quality free GPU path:
# portrait storyboard -> Wan 2.1 I2V 1.3B -> Hindi voice -> generated music -> 9:16 short.
# The 1.3B I2V model is used instead of AnimateDiff text-to-video because the
# first frame anchors the character design and improves scene continuity.

subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "diffusers>=0.36.0",
    "transformers>=4.49.0",
    "accelerate>=1.5.0",
    "imageio[ffmpeg]",
    "edge-tts",
    "pillow",
])

import asyncio
import math
import wave

import torch
from PIL import Image, ImageDraw
from diffusers import WanImageToVideoPipeline
from diffusers.utils import export_to_video

OUT = Path("/kaggle/working")
FRAMES = 49
FPS = 16
MODEL_WIDTH = 832
MODEL_HEIGHT = 480
PORTRAIT_WIDTH = 480
PORTRAIT_HEIGHT = 832
MODEL_ID = "engineerA314/Wan2.1-Fun-V1.1-1.3B-InP-Diffusers"

print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NONE")
if not torch.cuda.is_available():
    raise RuntimeError("Kaggle did not provide a CUDA GPU")

story = {
    "title": "Chiku Aur Chamkili Chabi",
    "character": "cute little white rabbit, pink inner ears, blue jacket, round sparkling eyes",
    "scenes": [
        {"visual": "The rabbit discovers a glowing golden key on a sunny path in a magical forest.", "narration": "Chiku ko jungle mein ek chamakti hui sunehri chabi milti hai."},
        {"visual": "The same rabbit gently holds the glowing key and looks around curiously among colorful flowers.", "narration": "Chiku chabi ko dhyan se dekhta hai aur sochta hai, yeh kis kaam ki hogi?"},
        {"visual": "The same rabbit meets a tiny friendly squirrel; both friends happily search for a small golden lock.", "narration": "Tabhi uski nanhi dost gilhari aati hai, aur dono milkar tala dhoondhne lagte hain."},
        {"visual": "The same rabbit and squirrel discover a tiny sparkling golden door hidden behind bright flowers.", "narration": "Rang-birange phoolon ke peeche unhe ek chhota sa sunehra darwaza milta hai."},
        {"visual": "The same rabbit carefully puts the glowing key into the tiny golden door; warm magical light appears.", "narration": "Chiku chabi ghumata hai, aur darwaza chamakti roshni ke saath khul jata hai."},
        {"visual": "The same rabbit and squirrel see a colorful basket of toys inside the magical room and celebrate together.", "narration": "Andar dono ke liye rang-birange khilonon ki pyari tokri rakhi hoti hai."},
        {"visual": "The same rabbit and squirrel wave happily with the toys in the magical forest, joyful friendship ending.", "narration": "Chiku muskurata hai: milkar koshish karne se mushkil kaam bhi aasan ho jata hai."},
    ],
}

STYLE = (
    "premium 3D preschool animated film, cute rounded character design, soft cinematic lighting, "
    "colorful magical environment, polished family animation, adorable expressive face, clean shapes, "
    "gentle depth of field, smooth natural motion, no text, no subtitles, no watermark"
)
NEGATIVE = (
    "blurry, low quality, flicker, jitter, deformed face, distorted anatomy, extra limbs, duplicate character, "
    "changing clothes, changing colors, text, letters, logo, watermark, scary, dark, horror"
)


def make_storyboard_image(path: Path):
    # Build the anchor in portrait. Wan's recommended 480p I2V shape is landscape,
    # so the anchor is rotated only for inference and rotated back after generation.
    img = Image.new("RGB", (PORTRAIT_WIDTH, PORTRAIT_HEIGHT), (169, 222, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, PORTRAIT_WIDTH, int(PORTRAIT_HEIGHT * 0.66)), fill=(169, 222, 255))
    d.ellipse((-180, 180, 420, 720), fill=(126, 205, 135))
    d.ellipse((180, 210, 660, 760), fill=(103, 190, 120))
    d.polygon([(150, PORTRAIT_HEIGHT), (210, 280), (300, 280), (460, PORTRAIT_HEIGHT)], fill=(244, 219, 166))
    for x, y in [(60, 300), (110, 420), (350, 340), (390, 500), (445, 290)]:
        d.ellipse((x - 10, y - 10, x + 10, y + 10), fill=(255, 190, 205))
        d.ellipse((x - 5, y - 20, x + 5, y + 20), fill=(255, 245, 130))
    cx, cy = 225, 470
    d.ellipse((cx - 105, cy - 105, cx + 105, cy + 135), fill=(250, 250, 250))
    d.ellipse((cx - 80, cy - 220, cx - 25, cy - 80), fill=(250, 250, 250))
    d.ellipse((cx + 25, cy - 220, cx + 80, cy - 80), fill=(250, 250, 250))
    d.ellipse((cx - 60, cy - 198, cx - 40, cy - 105), fill=(245, 160, 185))
    d.ellipse((cx + 40, cy - 198, cx + 60, cy - 105), fill=(245, 160, 185))
    d.ellipse((cx - 55, cy - 20, cx - 35, cy), fill=(40, 55, 75))
    d.ellipse((cx + 35, cy - 20, cx + 55, cy), fill=(40, 55, 75))
    d.ellipse((cx - 16, cy + 12, cx + 16, cy + 34), fill=(235, 125, 145))
    d.rounded_rectangle((cx - 95, cy + 65, cx + 95, cy + 175), 30, fill=(74, 143, 225))
    d.ellipse((cx + 125, cy + 30, cx + 165, cy + 70), outline=(255, 215, 60), width=10)
    d.line((cx + 162, cy + 50, cx + 235, cy + 50), fill=(255, 215, 60), width=12)
    d.line((cx + 210, cy + 50, cx + 210, cy + 80), fill=(255, 215, 60), width=10)
    img.save(path, quality=95)


def make_music(path: Path, seconds: float):
    sr = 22050
    notes = [523.25, 659.25, 783.99, 659.25, 587.33, 698.46, 880.0, 698.46]
    total = int(sr * seconds)
    with wave.open(str(path), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        for i in range(total):
            t = i / sr
            f = notes[int(t * 4) % len(notes)]
            env = min(1.0, t * 4.0) * min(1.0, max(0.0, seconds - t) * 2.0)
            value = (0.035 * math.sin(2 * math.pi * f * t) + 0.018 * math.sin(2 * math.pi * f * 2 * t)) * env
            wav.writeframes(int(max(-1, min(1, value)) * 32767).to_bytes(2, "little", signed=True))


async def make_voice(text: str, path: Path):
    import edge_tts
    await edge_tts.Communicate(text, "hi-IN-MadhurNeural", rate="+8%", volume="+0%").save(str(path))


def ffmpeg(args):
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args])


# T4 is a FP16 GPU; use float16 rather than bfloat16 to avoid unsupported BF16 paths.
pipe = WanImageToVideoPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float16)
pipe.enable_sequential_cpu_offload()

clips = []
voices = []
for index, scene in enumerate(story["scenes"], start=1):
    first_frame = OUT / f"anchor_{index:02d}.png"
    raw_video = OUT / f"scene_raw_{index:02d}.mp4"
    video = OUT / f"scene_{index:02d}.mp4"
    voice = OUT / f"voice_{index:02d}.mp3"
    make_storyboard_image(first_frame)
    # Rotate portrait -> landscape only for the Wan model's recommended 480p shape.
    model_image = Image.open(first_frame).convert("RGB").rotate(90, expand=True)
    prompt = (
        f"{story['character']}, {scene['visual']}, {STYLE}. "
        "Keep the character identity, clothes, face, proportions and colors identical to the input image. "
        "Only animate the described action with subtle body movement and gentle camera motion."
    )
    print(f"Generating Wan I2V scene {index}/{len(story['scenes'])}...")
    with torch.inference_mode():
        result = pipe(
            image=model_image,
            prompt=prompt,
            negative_prompt=NEGATIVE,
            height=MODEL_HEIGHT,
            width=MODEL_WIDTH,
            num_frames=FRAMES,
            num_inference_steps=24,
            guidance_scale=5.0,
            generator=torch.Generator(device="cuda").manual_seed(1000 + index),
        )
    export_to_video(result.frames[0], str(raw_video), fps=FPS)
    # Rotate generated landscape video back to true 9:16 portrait.
    ffmpeg(["-i", str(raw_video), "-vf", "transpose=2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(video)])
    asyncio.run(make_voice(scene["narration"], voice))
    clips.append(video)
    voices.append(voice)
    del result, model_image
    torch.cuda.empty_cache()

scene_final = []
for i, (video, voice) in enumerate(zip(clips, voices), start=1):
    out = OUT / f"scene_audio_{i:02d}.mp4"
    ffmpeg(["-i", str(video), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)])
    scene_final.append(out)

concat = OUT / "concat.txt"
concat.write_text("\n".join(f"file '{p.name}'" for p in scene_final), encoding="utf-8")
joined = OUT / "joined.mp4"
ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])

music = OUT / "kids_music.wav"
make_music(music, len(story["scenes"]) * (FRAMES / FPS) + 1)
final = OUT / "toon_kids_wan_i2v_test.mp4"
ffmpeg([
    "-i", str(joined), "-i", str(music),
    "-filter_complex", "[1:a]volume=0.10[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
    "-map", "0:v:0", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
    "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final),
])
print("FINAL:", final)
print("SIZE:", final.stat().st_size)
