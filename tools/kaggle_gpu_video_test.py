import os
import subprocess
import sys

# Keep this first test intentionally small. It proves that the free Kaggle GPU
# can generate an actual MP4 before we connect it to the Toon Kids pipeline.
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

print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NONE")
if not torch.cuda.is_available():
    raise RuntimeError("Kaggle did not provide a CUDA GPU")

# Public SD1.5-compatible base model + AnimateDiff motion adapter.
BASE_MODEL = "Lykon/dreamshaper-8"
MOTION_MODEL = "guoyww/animatediff-motion-adapter-v1-5-2"

adapter = MotionAdapter.from_pretrained(
    MOTION_MODEL,
    torch_dtype=torch.float16,
)

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

prompt = (
    "cute pink cartoon kitten wearing a blue jacket and yellow shoes, "
    "big sparkling blue eyes, magical colorful garden, children's 3D cartoon, "
    "bright cheerful lighting, playful cinematic animation, consistent character"
)
negative = "blurry, distorted, extra limbs, text, watermark, scary, dark"

with torch.inference_mode():
    result = pipe(
        prompt=prompt,
        negative_prompt=negative,
        num_frames=16,
        guidance_scale=7.0,
        num_inference_steps=8,
        height=256,
        width=256,
    )

video_path = "/kaggle/working/toon_kids_kaggle_gpu_test.mp4"
export_to_video(result.frames[0], video_path, fps=8)

print("Created:", video_path)
print("Size:", os.path.getsize(video_path))
