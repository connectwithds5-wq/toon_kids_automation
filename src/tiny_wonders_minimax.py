import concurrent.futures
import json
import os
import shutil
import subprocess
from pathlib import Path

from google import genai
from google.genai import types
from gradio_client import Client

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "tiny_wonder.mp4"
META = BASE / "tiny_wonder_metadata.json"
HISTORY = BASE / "story_history.json"
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")
HF_TOKEN = os.getenv("HF_TOKEN") or None
H3_SPACE = os.getenv("MINIMAX_H3_SPACE", "multimodalart/minimax-h3")
# H3 currently runs its generator on ZeroGPU xlarge (2x quota). An 8s/10-step
# request fits much more safely inside the 5-minute free daily quota.
DURATION = int(os.getenv("MINIMAX_H3_DURATION", "8"))
FINAL_DURATION = int(os.getenv("MINIMAX_H3_FINAL_DURATION", "10"))
CANVAS = os.getenv("MINIMAX_H3_CANVAS", "544x960 · 9:16 fast")
STEPS = int(os.getenv("MINIMAX_H3_STEPS", "10"))

IDEAS = [
    "A tiny white rabbit waters a pink flower; the flower grows and reveals a tiny glowing wooden door.",
    "A little fox blows a dandelion; the floating seeds become tiny glowing stars around its head.",
    "A baby penguin rolls a snowball; it grows into a miniature sparkling snow castle.",
    "A squirrel discovers a giant strawberry; one bite makes a tiny strawberry tree bloom beside it.",
    "A kitten touches a puddle; the puddle becomes a mirror whose reflection waves back independently.",
    "A baby bear hugs a tree; the tree lights up and gently illuminates the whole forest.",
    "A puppy catches a falling cloud; it squeezes into a soft little cloud ball that bounces back.",
    "A tiny mouse rings a little bell; the moon answers with a shower of colorful sparkles.",
    "A hedgehog opens an umbrella; raindrops land on it and the umbrella blooms into flowers.",
    "A cheerful frog jumps over a puddle; the splash turns into a tiny rainbow bridge."
]


def recent_titles():
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x.get("title", "") if isinstance(x, dict) else str(x) for x in data[-20:]]
    except Exception:
        pass
    return []


def make_concept():
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY is required")
    recent = recent_titles()
    seed_ideas = "\n".join(f"{i+1}. {x}" for i, x in enumerate(IDEAS))
    prompt = f"""
You are the creative director of a premium short-form animation channel called Tiny Wonders.
Create ONE original {DURATION}-second, family-safe, visually magical micro-story.
Use one adorable animal only. No dialogue is required.
The entire story must be understandable visually without narration.

FORMAT:
0-2s = instant visual hook
2-5s = simple cute action/discovery
5-7s = surprising magical transformation
7-{DURATION}s = delightful payoff that can visually loop

QUALITY TARGET:
High-end cinematic 3D animation, Google Flow/Veo-style visual polish, rich scenery,
beautiful lighting, expressive eyes, physically believable motion, strong composition,
clear foreground/midground/background depth. Keep one character and its appearance stable.
Avoid complex choreography; favor one clear continuous action that a video model can execute well.

POSSIBLE STARTING IDEAS:
{seed_ideas}

Do not copy a previous title: {json.dumps(recent, ensure_ascii=False)}
Return ONLY valid JSON:
{{
  "title": "short catchy title",
  "character": "exact animal appearance and colors",
  "setting": "specific cinematic environment",
  "hook": "what happens in first 2 seconds",
  "action": "main continuous action",
  "twist": "magical transformation",
  "ending": "happy satisfying ending",
  "prompt": "ONE detailed English video-generation prompt describing the full {DURATION}-second shot, including camera, lighting, animation and synchronized sound",
  "caption": "short social caption",
  "moral": "optional one-line positive idea"
}}
"""
    client = genai.Client(api_key=GEMINI_KEY)
    for _ in range(3):
        r = client.models.generate_content(
            model=TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.9,
                response_mime_type="application/json",
            ),
        )
        concept = json.loads(r.text)
        if concept.get("prompt") and concept.get("title"):
            return concept
    raise RuntimeError("Gemini did not return a valid Tiny Wonders concept")


def generate_video(concept):
    client = Client(H3_SPACE, token=HF_TOKEN)
    try:
        result = client.predict(
            prompt=concept["prompt"],
            image_path=None,
            last_image_path=None,
            canvas=CANVAS,
            duration=DURATION,
            steps=STEPS,
            seed=42,
            upsample=False,
            api_name="/generate",
        )
    except concurrent.futures.CancelledError as exc:
        raise RuntimeError(
            "MiniMax H3 request was cancelled by the Gradio/ZeroGPU stream. "
            "This usually means the ZeroGPU worker/queue or quota reservation was not able to complete the request. "
            "The pipeline now uses an 8s generation to stay within the free quota."
        ) from exc
    if not isinstance(result, (list, tuple)) or not result:
        raise RuntimeError(f"Unexpected MiniMax H3 response: {result!r}")
    video = result[0]
    if isinstance(video, dict):
        video = video.get("path") or video.get("url")
    source = Path(str(video))
    if not source.is_file():
        raise FileNotFoundError(f"MiniMax H3 returned no local video: {video!r}")

    if FINAL_DURATION <= DURATION:
        shutil.copy2(source, OUT)
        return OUT

    # Keep the public deliverable at 10 seconds without spending extra H3 quota.
    # The generated clip is extended by freezing its final frame; H3 soundtrack is
    # preserved and padded with silence for the short tail.
    extension = FINAL_DURATION - DURATION
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(source),
            "-vf", f"tpad=stop_mode=clone:stop_duration={extension}",
            "-af", f"apad=pad_dur={extension}",
            "-t", str(FINAL_DURATION),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(OUT),
        ],
        check=True,
    )
    return OUT


def main():
    concept = make_concept()
    print("TINY WONDER:", json.dumps(concept, ensure_ascii=False, indent=2))
    print(
        f"MiniMax H3 settings: canvas={CANVAS}, generation={DURATION}s, "
        f"steps={STEPS}, final={FINAL_DURATION}s"
    )
    video = generate_video(concept)
    concept["generation_duration_seconds"] = DURATION
    concept["final_duration_seconds"] = FINAL_DURATION
    META.write_text(json.dumps(concept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FINAL: {video}")
    print(f"TITLE: {concept['title']}")
    print(f"MORAL: {concept.get('moral', '')}")


if __name__ == "__main__":
    main()
