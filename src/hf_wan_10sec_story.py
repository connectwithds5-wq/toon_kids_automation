import os
import shutil
import subprocess
from pathlib import Path

from gradio_client import Client, handle_file
from google import genai
from google.genai import types
from PIL import Image

from toon_kids_story import WORK, local_story, load_history, scene_image

SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or None
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
GEMINI_ENABLED = os.getenv("GEMINI_IMAGE_ENABLED", "true").lower() == "true"
ZIMAGE_SPACE = os.getenv("ZIMAGE_SPACE", "mrfakename/Z-Image-Turbo")
ZIMAGE_ENABLED = os.getenv("ZIMAGE_ENABLED", "true").lower() == "true"
ZIMAGE_WIDTH = int(os.getenv("ZIMAGE_WIDTH", "864"))
ZIMAGE_HEIGHT = int(os.getenv("ZIMAGE_HEIGHT", "1536"))
ZIMAGE_STEPS = int(os.getenv("ZIMAGE_STEPS", "9"))
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_10sec_story.mp4"))
CLIP_SECONDS = 3.5
FINAL_SECONDS = 10.0

# Runtime circuit breakers. Hard quota/configuration failures are not retried
# for every scene; the next provider is selected immediately.
_gemini_disabled_reason = None
_zimage_disabled_reason = None
_zimage_client = None


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


def extract_image_path(result):
    if isinstance(result, dict):
        for key in ("image", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
            try:
                return extract_image_path(value)
            except RuntimeError:
                pass
        raise RuntimeError(f"No image path in result: {result!r}")
    if isinstance(result, (tuple, list)):
        for item in result:
            if isinstance(item, str) and (Path(item).is_file() or item.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))):
                return item
            try:
                return extract_image_path(item)
            except RuntimeError:
                pass
        raise RuntimeError(f"No image path in result: {result!r}")
    if isinstance(result, str) and result:
        return result
    raise RuntimeError(f"Unsupported image result: {result!r}")


def _generate_gemini_anchor(story, scene, output_path, reference_path=None):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=GEMINI_API_KEY)
    character = story.get("character", "cute cartoon animal")
    action = scene.get("visual", "")
    camera = scene.get("camera", "cinematic tracking shot")

    prompt = f"""
Create a premium cinematic 3D animated children's movie frame in a vertical 9:16 composition.
This is an original family-friendly animated film, not a flat illustration and not a vector/cartoon icon.

MAIN CHARACTER — keep this exact identity in every scene:
{character}

SCENE ACTION:
{action}

CAMERA / COMPOSITION:
{camera}. Strong cinematic composition with foreground, midground and background depth; natural lens perspective;
tasteful shallow depth of field; subject clearly separated from background.

VISUAL STYLE:
High-end theatrical 3D animation, expressive but believable character, detailed fur/materials, physically based textures,
soft global illumination, volumetric light rays, subtle rim lighting, realistic shadows, atmospheric perspective,
rich environment detail, cinematic color grading, beautiful bokeh, polished feature-film rendering,
emotionally warm children's adventure movie.
Use a slightly low cinematic camera angle where appropriate, dynamic staging, and intentional negative space.

IMPORTANT:
Do NOT make it look like a 2D/vector drawing, sticker, emoji, flat graphic, clip-art, children's worksheet,
or simple geometric cartoon. No text, no captions, no letters, no logo, no watermark.
No borders or UI elements.
""".strip()

    contents = [prompt]
    if reference_path and reference_path.is_file():
        with Image.open(reference_path) as reference_image:
            contents.append(reference_image.copy())
        contents.append(
            "Use the supplied reference image ONLY to preserve the main character's identity, face, "
            "colors, clothing and proportions. Redesign the scene as a premium cinematic 3D film frame; "
            "do not copy the flat/vector rendering style of the reference."
        )

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio="9:16",
            image_size="2K",
        ),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    response = client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=contents,
        config=config,
    )

    for part in response.parts:
        if part.inline_data is not None:
            part.as_image().save(output_path)
            return
    raise RuntimeError("Gemini image generation returned no image data")


def _generate_zimage_anchor(story, scene, index, output_path):
    global _zimage_client
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN is required for the free ZeroGPU image fallback")

    if _zimage_client is None:
        _zimage_client = Client(ZIMAGE_SPACE, token=HF_TOKEN)

    character = story.get("character", "cute animated animal")
    action = scene.get("visual", "")
    camera = scene.get("camera", "cinematic tracking shot")
    prompt = (
        "Premium theatrical 3D animated children's movie frame, vertical 9:16. "
        "High-end feature-film CGI, expressive believable character, detailed materials, soft global illumination, "
        "volumetric sunlight, rim lighting, realistic shadows, atmospheric perspective, cinematic color grading, "
        "shallow depth of field, beautiful bokeh, natural lens perspective, rich environment detail. "
        f"Main character: {character}. Scene: {action}. Camera: {camera}. "
        "Keep the character cute, consistent and family-friendly. No text, no logo, no watermark. "
        "Absolutely avoid flat vector art, sticker art, emoji style, clip-art or worksheet illustration."
    )
    negative = (
        "flat vector, 2D illustration, sticker, emoji, clip-art, worksheet, simplistic geometric cartoon, "
        "low quality, blurry, deformed anatomy, extra limbs, duplicate character, text, logo, watermark"
    )

    result = _zimage_client.predict(
        prompt,
        ZIMAGE_HEIGHT,
        ZIMAGE_WIDTH,
        ZIMAGE_STEPS,
        1000 + index,
        True,
        api_name="/generate_image",
    )
    source = Path(extract_image_path(result))
    if not source.is_file():
        raise FileNotFoundError(f"Z-Image output does not exist: {source}")
    shutil.copy2(source, output_path)


def _generate_local_anchor(story, scene, index, output_path):
    """Deterministic zero-quota fallback using the repo's existing renderer."""
    scene_image(story, scene, index, output_path)


def generate_cinematic_anchor(story, scene, index, output_path, reference_path=None):
    global _gemini_disabled_reason, _zimage_disabled_reason

    if GEMINI_ENABLED and _gemini_disabled_reason is None:
        try:
            print(f"[Scene {index + 1}/3] Trying Gemini cinematic 3D anchor...")
            _generate_gemini_anchor(story, scene, output_path, reference_path)
            return "gemini"
        except Exception as exc:
            message = str(exc).replace("\n", " ")
            _gemini_disabled_reason = message[:500]
            print("[Image fallback] Gemini unavailable; moving to free ZeroGPU image generation.")
            print(f"[Image fallback] Gemini reason: {message[:500]}")

    if ZIMAGE_ENABLED and _zimage_disabled_reason is None:
        try:
            print(f"[Scene {index + 1}/3] Generating free Z-Image-Turbo cinematic anchor...")
            _generate_zimage_anchor(story, scene, index, output_path)
            return "z-image-turbo"
        except Exception as exc:
            message = str(exc).replace("\n", " ")
            _zimage_disabled_reason = message[:500]
            print("[Image fallback] Z-Image-Turbo unavailable; using deterministic local renderer.")
            print(f"[Image fallback] Z-Image reason: {message[:500]}")

    _generate_local_anchor(story, scene, index, output_path)
    return "local"


def make_clip(client, story, scene, index, character_reference):
    image_path = WORK / f"wan_10sec_scene_{index + 1}.png"
    clip_path = WORK / f"wan_10sec_scene_{index + 1}.mp4"

    print(f"[Scene {index + 1}/3] Creating cinematic 3D anchor image...")
    reference = character_reference if index > 0 and character_reference.is_file() else None
    source_type = generate_cinematic_anchor(story, scene, index, image_path, reference)
    print(f"[Scene {index + 1}/3] Anchor ready via {source_type} renderer.")

    if index == 0:
        shutil.copy2(image_path, character_reference)

    prompt = (
        "Premium theatrical 3D animated children's movie, cinematic film quality. "
        "Preserve the EXACT same character identity, face, colors, clothing and proportions from the input image. "
        f"Character: {story.get('character', 'cute cartoon animal')}. "
        f"Scene action: {scene.get('visual', '')}. "
        f"Camera movement: {scene.get('camera', 'smooth cinematic tracking shot')}. "
        "Use natural physically believable motion, expressive acting, stable anatomy and face, cinematic depth, "
        "foreground/midground/background separation, volumetric light, subtle motion blur, soft bokeh, realistic shadows, "
        "polished feature-film rendering, warm cinematic color grade. Do not flatten the scene into a simple cartoon. "
        "No text, subtitles, logo or watermark."
    )[:1100]

    negative_prompt = (
        "flat vector art, 2D illustration, sticker, emoji, clip-art, worksheet style, simplistic shapes, blurry, low quality, "
        "out of focus, distorted face, deformed body, extra limbs, missing limbs, bad anatomy, duplicate character, "
        "character morphing, face morphing, flicker, jitter, frame tearing, unstable clothing, unstable colors, text, letters, "
        "subtitles, logo, watermark, gray frame, noise"
    )

    print(f"[Scene {index + 1}/3] Generating {CLIP_SECONDS}s Wan 2.2 cinematic clip...")
    result = client.predict(
        handle_file(str(image_path)), prompt, 6, negative_prompt, CLIP_SECONDS,
        1.0, 1.0, 1000 + index, False, api_name="/generate_video",
    )
    source = Path(extract_video_path(result))
    if not source.is_file():
        raise FileNotFoundError(f"HF video does not exist: {source}")
    shutil.copy2(source, clip_path)
    return clip_path


def concat_and_trim(clips):
    concat_file = WORK / "wan_10sec_concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clips), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-t", str(FINAL_SECONDS), "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT),
    ]
    print("Assembling the 10-second cinematic story...")
    subprocess.run(cmd, check=True)


def main():
    WORK.mkdir(exist_ok=True)
    story = local_story(load_history())
    scenes = story.get("scenes", [])[:3]
    if len(scenes) < 3:
        raise RuntimeError("The selected story must contain at least 3 scenes.")
    print(f"Story: {story['title']}")
    print("Plan: 3 cinematic story scenes x 3.5s, then trim to exactly 10s.")
    client = Client(SPACE, token=HF_TOKEN)
    character_reference = WORK / "wan_cinematic_character_reference.png"
    clips = [make_clip(client, story, scene, i, character_reference) for i, scene in enumerate(scenes)]
    concat_and_trim(clips)
    subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
        "-of", "default=noprint_wrappers=1", str(OUT)
    ], check=True)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
