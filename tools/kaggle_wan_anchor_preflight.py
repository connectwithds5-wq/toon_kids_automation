import gc
import subprocess
import sys
from pathlib import Path

# SAFE PREFLIGHT: generates only the AI character reference + scene anchors.
# It intentionally does NOT load or call Wan, so visual quality can be reviewed before spending video quota.
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "diffusers>=0.36.0", "transformers>=4.49.0", "accelerate>=1.5.0",
    "safetensors", "pillow", "google-genai", "google-api-python-client", "google-auth",
])

import torch
from PIL import Image, ImageDraw, ImageFont
from diffusers import AutoPipelineForText2Image, AutoPipelineForImage2Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from toon_kids_story import local_story, load_history  # noqa: E402

OUT = Path("/kaggle/working/anchors")
IMAGE_MODEL = "segmind/SSD-1B"
WIDTH, HEIGHT = 480, 832
ANCHOR_W, ANCHOR_H = 512, 768

STYLE = (
    "high-end 3D preschool animated movie, premium family animation, cute rounded shapes, "
    "soft cinematic lighting, rich colorful environment, expressive adorable face, polished stylized materials, "
    "gentle depth of field, appealing children's cartoon, consistent character design"
)
NEGATIVE = (
    "text, letters, subtitles, logo, watermark, blurry, low quality, duplicate character, extra limbs, "
    "deformed face, malformed hands, scary, horror, dark, photorealistic, flat vector art, sketch, "
    "character morphing, changing clothes, changing colors, inconsistent face, inconsistent proportions"
)


def character_prompt(story):
    return (
        f"Full-body character reference of {story.get('character', 'a cute little cartoon animal')}. "
        f"{STYLE}. Give the hero a simple memorable silhouette, large expressive eyes, clearly defined "
        "clothing/accessories, friendly preschool-safe appearance, consistent colors and proportions. "
        "Bright neutral storybook meadow, centered, full body visible, front three-quarter view, clean studio-like composition."
    )


def scene_prompt(story, scene, index):
    return (
        f"{story.get('character', 'cute cartoon animal')}. Scene {index}: {scene.get('visual', '')}. "
        f"{STYLE}. Preserve the exact same hero identity, face, fur/skin colors, clothes, accessories, "
        "body proportions and eye style from the reference image. Build the described environment around the hero. "
        "Show one clear readable action pose, natural staging, appealing foreground and background separation. "
        "Vertical portrait composition. No text or writing."
    )


def make_contact_sheet(images, title):
    thumb_w, thumb_h = 240, 416
    margin, label_h = 16, 34
    cols = 2
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w + (cols + 1) * margin,
                               rows * (thumb_h + label_h) + (rows + 1) * margin + 48), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, 12), title, fill="black")
    for n, path in enumerate(images):
        r, c = divmod(n, cols)
        x = margin + c * (thumb_w + margin)
        y = 48 + margin + r * (thumb_h + label_h + margin)
        im = Image.open(path).convert("RGB")
        im.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(im, (x + (thumb_w - im.width) // 2, y))
        draw.text((x, y + thumb_h + 8), path.stem.replace("_", " ").title(), fill="black")
    return sheet


def main():
    if not torch.cuda.is_available():
        raise RuntimeError("Kaggle GPU is required")
    OUT.mkdir(parents=True, exist_ok=True)
    history = load_history()
    story = local_story(history)
    print("📖 Story:", story["title"])
    print("🎭 Character:", story.get("character", ""))
    print("🛡️ PREFLIGHT ONLY — Wan will NOT be loaded or called.")

    pipe = AutoPipelineForText2Image.from_pretrained(
        IMAGE_MODEL, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    pipe.enable_model_cpu_offload()

    character_path = OUT / "character_reference.png"
    print("🧑‍🎨 Generating character reference...")
    image = pipe(
        prompt=character_prompt(story),
        negative_prompt=NEGATIVE,
        height=ANCHOR_H,
        width=ANCHOR_W,
        num_inference_steps=4,
        guidance_scale=6.0,
        generator=torch.Generator(device="cpu").manual_seed(4242),
    ).images[0]
    image.save(character_path)

    img2img = AutoPipelineForImage2Image.from_pretrained(
        IMAGE_MODEL, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    img2img.enable_model_cpu_offload()
    anchors = []
    for i, scene in enumerate(story["scenes"], start=1):
        out = OUT / f"anchor_{i:02d}.png"
        print(f"🖼️ Scene anchor {i}/{len(story['scenes'])}...")
        result = img2img(
            prompt=scene_prompt(story, scene, i),
            negative_prompt=NEGATIVE,
            image=image,
            strength=0.48,
            height=ANCHOR_H,
            width=ANCHOR_W,
            num_inference_steps=4,
            guidance_scale=6.0,
            generator=torch.Generator(device="cpu").manual_seed(9000 + i),
        ).images[0]
        result = result.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        result.save(out)
        anchors.append(out)

    del img2img, pipe, image
    gc.collect()
    torch.cuda.empty_cache()

    # Include the reference plus all anchors in one review sheet.
    sheet = make_contact_sheet(anchors, f"{story['title']} — 7 scene anchors")
    sheet.save(OUT / "anchors_contact_sheet.jpg", quality=92)
    (OUT / "story_used.txt").write_text(
        story["title"] + "\n" + story.get("moral", ""), encoding="utf-8"
    )
    print("ANCHORS_READY:", OUT)
    print("WAN_CALLED: NO")


if __name__ == "__main__":
    main()
