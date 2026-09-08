import os
import subprocess
import sys
from pathlib import Path

subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "diffusers>=0.30.0",
    "transformers>=4.44.0",
    "accelerate>=0.34.0",
    "imageio[ffmpeg]",
])

import torch
from diffusers import AnimateDiffPipeline, MotionAdapter, DDIMScheduler
from diffusers.utils import export_to_video

OUT = Path("/kaggle/working")
FPS = 4
FRAMES = 16
WIDTH = 360
HEIGHT = 640

print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NONE")
if not torch.cuda.is_available():
    raise RuntimeError("Kaggle did not provide a CUDA GPU")

BASE_MODEL = "Lykon/dreamshaper-8"
MOTION_MODEL = "guoyww/animatediff-motion-adapter-v1-5-2"

adapter = MotionAdapter.from_pretrained(MOTION_MODEL, torch_dtype=torch.float16)
pipe = AnimateDiffPipeline.from_pretrained(
    BASE_MODEL,
    motion_adapter=adapter,
    torch_dtype=torch.float16,
)
pipe.scheduler = DDIMScheduler.from_config(
    pipe.scheduler.config,
    clip_sample=False,
    timestep_spacing="linspace",
    beta_schedule="linear",
)
pipe = pipe.to("cuda")
pipe.enable_vae_slicing()
pipe.enable_attention_slicing()

character = (
    "cute little white rabbit, pink ears, blue jacket, round sparkling eyes, "
    "same character design in every scene, adorable children's 3D cartoon"
)
style = (
    "bright colorful preschool animation, soft rounded shapes, cheerful lighting, "
    "clean composition, cinematic kids cartoon, high detail, consistent style"
)
negative = "blurry, distorted, extra limbs, duplicate character, text, watermark, scary, dark, cropped face"

scenes = [
    "The rabbit happily discovers a glowing golden key on a path in a magical forest.",
    "The rabbit carefully holds the glowing key and looks around, wondering what it opens.",
    "A friendly little squirrel joins the rabbit and they walk together searching for the key's lock.",
    "Behind colorful flowers, the rabbit and squirrel discover a tiny sparkling golden door.",
    "The rabbit puts the glowing key into the tiny golden door and the door opens with magical light.",
    "Inside is a beautiful basket full of colorful toys, and both friends celebrate happily.",
    "The rabbit and squirrel wave together with the toys, smiling and celebrating friendship and teamwork.",
]

clips = []
for index, scene in enumerate(scenes, start=1):
    prompt = f"{character}, {scene} {style}"
    print(f"Generating scene {index}/{len(scenes)}")
    with torch.inference_mode():
        result = pipe(
            prompt=prompt,
            negative_prompt=negative,
            num_frames=FRAMES,
            guidance_scale=7.0,
            num_inference_steps=8,
            height=HEIGHT,
            width=WIDTH,
        )
    path = OUT / f"scene_{index:02d}.mp4"
    export_to_video(result.frames[0], str(path), fps=FPS)
    clips.append(path)
    print("Created", path, path.stat().st_size)

concat_file = OUT / "concat.txt"
concat_file.write_text("\n".join(f"file '{p.name}'" for p in clips), encoding="utf-8")
final_path = OUT / "toon_kids_production_test.mp4"

subprocess.check_call([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", str(concat_file),
    "-vf", "fps=24,format=yuv420p",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-movflags", "+faststart", str(final_path),
])

print("FINAL:", final_path)
print("SIZE:", final_path.stat().st_size)
