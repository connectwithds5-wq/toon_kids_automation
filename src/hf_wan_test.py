import os
import shutil
from pathlib import Path

from gradio_client import Client, handle_file

from toon_kids_story import WORK, local_story, load_history, scene_image

SPACE = os.getenv("HF_WAN_SPACE", "alexcheng0072/wan27-free-video-generator")
HF_TOKEN = os.getenv("HF_TOKEN") or None
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_test.mp4"))


def _extract_video_path(result):
    """Normalize common Gradio return shapes to a local video filepath."""
    if isinstance(result, dict):
        # Current Space returns: {"video": "/tmp/.../video.mp4"}
        for key in ("video", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"Hugging Face returned a dict without a video path: {result!r}")

    if isinstance(result, (tuple, list)):
        # Handle both [path] and [(path, metadata)] style responses.
        for item in result:
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

    print(f"Connecting to Hugging Face Space: {SPACE}")
    client = Client(SPACE, token=HF_TOKEN)
    print("Submitting 3-second portrait Wan 2.2 generation...")

    # The live Space exposes a simplified API. It expects the aspect-ratio
    # choice string, not raw height/width values.
    # Portrait is exactly the public choice "480x832".
    result = client.predict(
        handle_file(str(image_path)),
        prompt,
        "480x832",
        3,
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
