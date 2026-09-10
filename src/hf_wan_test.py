import os
import shutil
from pathlib import Path

from gradio_client import Client, handle_file

from toon_kids_story import WORK, local_story, load_history, scene_image

# Fast Wan 2.2 14B I2V ZeroGPU Space with Lightning LoRA.
# It accepts an image + prompt and returns (video_path, seed).
SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_test.mp4"))


def _extract_video_path(result):
    """Normalize common Gradio return shapes to a local video filepath."""
    if isinstance(result, dict):
        for key in ("video", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"Hugging Face returned a dict without a video path: {result!r}")

    if isinstance(result, (tuple, list)):
        for item in result:
            if isinstance(item, str) and item:
                # The Space returns (video_path, seed); don't treat the seed as a path.
                if item.endswith((".mp4", ".webm", ".mov", ".mkv")) or Path(item).is_file():
                    return item
            try:
                path = _extract_video_path(item)
                if path:
                    return path
            except RuntimeError:
                continue
        raise RuntimeError(f"Hugging Face returned no video path in: {result!r}")

    if isinstance(result, str) and result:
        return result

    raise RuntimeError(f"Hugging Face returned an unsupported result: {result!r}")


def main():
    WORK.mkdir(exist_ok=True)
    history = load_history()
    story = local_story(history)
    scene = story["scenes"][0]

    image_path = WORK / "wan_test_first_frame.png"
    print(f"Story: {story['title']}")
    print("Creating the first cartoon frame...")
    scene_image(story, scene, 0, image_path)

    prompt = (
        "3D cartoon children's story animation, cute friendly animal character, "
        f"{story.get('character', 'cute cartoon animal')}, {scene.get('visual', '')}. "
        "Bright colorful kids animation, expressive face, smooth natural movement, "
        "gentle camera motion, consistent character appearance, playful magical atmosphere, "
        "high quality animated film style, no text, no subtitles, no watermark."
    )[:600]

    negative_prompt = (
        "static, blurry, low quality, distorted face, deformed body, extra limbs, "
        "bad hands, flicker, jitter, text, subtitles, watermark, gray image, "
        "duplicate character, messy background"
    )

    print(f"Connecting to Hugging Face Space: {SPACE}")
    client = Client(SPACE, token=HF_TOKEN)
    print("Submitting 3.5-second portrait Wan 2.2 14B I2V generation (6-step Lightning)...")

    # Current Space API: generate_video(image, prompt, steps, negative_prompt,
    # duration_seconds, guidance_scale, guidance_scale_2, seed, randomize_seed).
    # The Space automatically resizes portrait inputs to a supported resolution.
    result = client.predict(
        handle_file(str(image_path)),
        prompt,
        6,
        negative_prompt,
        3.5,
        1.0,
        1.0,
        42,
        True,
        api_name="/generate_video",
    )

    print(f"HF result: {result!r}")
    video_path = _extract_video_path(result)

    source = Path(video_path)
    if not source.is_file():
        raise FileNotFoundError(f"Hugging Face returned a video path that does not exist: {source}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, OUT)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
