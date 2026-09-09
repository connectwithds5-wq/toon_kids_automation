import os
import shutil
from pathlib import Path

from gradio_client import Client, handle_file

from toon_kids_story import WORK, local_story, load_history, scene_image

SPACE = os.getenv("HF_WAN_SPACE", "alexcheng0072/wan27-free-video-generator")
HF_TOKEN = os.getenv("HF_TOKEN") or None
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_test.mp4"))


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
    result = client.predict(
        input_image=handle_file(str(image_path)),
        prompt=prompt,
        aspect_ratio="480x832",
        duration_input=3,
        api_name="/generate_video",
    )

    video_path = result[0] if isinstance(result, (tuple, list)) else result
    if not video_path:
        raise RuntimeError(f"Hugging Face returned no video: {result!r}")

    print(f"HF result: {video_path}")
    shutil.copy2(video_path, OUT)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
