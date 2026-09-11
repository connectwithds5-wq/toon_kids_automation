import asyncio
import math
import os
import shutil
import subprocess
import wave
from pathlib import Path

from gradio_client import Client, handle_file
from google import genai
from google.genai import types
from PIL import Image

from toon_kids_story import WORK, local_story, load_history, scene_image
from nursery_rhyme import local_rhyme

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
CINEMATIC_ONLY = os.getenv("CINEMATIC_ONLY", "true").lower() == "true"
CONTENT_MODE = os.getenv("CONTENT_MODE", "story").lower()
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_10sec_story.mp4"))
CLIP_SECONDS = 3.5
FINAL_SECONDS = 10.0

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
    character = story.get("character", "cute animated animal")
    action = scene.get("visual", "")
    camera = scene.get("camera", "cinematic tracking shot")
    prompt = f"""
Create a premium feature-film CGI still from an original children's nursery-rhyme movie, vertical 9:16.
The image MUST look like high-end theatrical 3D computer graphics, not a drawing.
Use physically based materials, detailed fur, realistic surface shading, soft global illumination,
volumetric light, cinematic rim light, natural lens perspective, depth of field, bokeh,
atmospheric perspective, realistic shadows, rich production-design detail and professional film color grading.
No visible ink outlines. No flat fills. No poster/vector treatment.
MAIN CHARACTER (identity must remain consistent): {character}
SCENE ACTION: {action}
CAMERA: {camera}
The frame should feel like a polished studio animated musical: dimensional character, real depth,
believable lighting, foreground/midground/background separation, joyful child-friendly staging.
ABSOLUTELY NO: 2D art, vector art, flat cartoon, sticker, emoji, clip-art, worksheet,
simple geometric shapes, cel-shaded poster, text, captions, letters, logo, watermark, UI or borders.
""".strip()
    contents = [prompt]
    if reference_path and reference_path.is_file():
        with Image.open(reference_path) as reference_image:
            contents.append(reference_image.copy())
        contents.append(
            "Use this reference ONLY for the character's identity, face, colors, clothing and proportions. "
            "Re-render everything as high-end theatrical 3D CGI with physically based materials and cinematic lighting. "
            "Do not inherit the reference's illustration or vector rendering style."
        )
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio="9:16", image_size="2K"),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    response = client.models.generate_content(model=GEMINI_IMAGE_MODEL, contents=contents, config=config)
    for part in response.parts:
        if part.inline_data is not None:
            part.as_image().save(output_path)
            return
    raise RuntimeError("Gemini image generation returned no image data")


def _generate_zimage_anchor(story, scene, index, output_path):
    global _zimage_client
    if _zimage_client is None:
        if HF_TOKEN:
            print("[Z-Image] HF_TOKEN configured; using authenticated ZeroGPU session.")
            _zimage_client = Client(ZIMAGE_SPACE, token=HF_TOKEN)
        else:
            print("[Z-Image] HF_TOKEN not configured; using anonymous ZeroGPU session.")
            print("[Z-Image] Anonymous access has a smaller daily quota; add HF_TOKEN later for higher quota/priority.")
            _zimage_client = Client(ZIMAGE_SPACE)
    character = story.get("character", "cute animated animal")
    action = scene.get("visual", "")
    camera = scene.get("camera", "cinematic tracking shot")
    prompt = (
        "MASTER STYLE: high-end theatrical 3D CGI feature-film render. Vertical 9:16. "
        "This is a frame from a major studio animated nursery-rhyme movie, rendered as dimensional computer graphics. "
        "Physically based materials, detailed soft fur, realistic skin/material response, global illumination, "
        "volumetric god rays, cinematic rim lighting, natural 35mm lens perspective, shallow depth of field, "
        "beautiful optical bokeh, atmospheric perspective, realistic contact shadows, detailed production design, "
        "professional cinematic color grade, rich contrast, filmic highlights. No ink outlines and no flat fills. "
        f"MAIN CHARACTER: {character}. SCENE: {action}. CAMERA: {camera}. "
        "Create a joyful musical-film composition with clear action and strong foreground/midground/background depth. "
        "Keep the character cute, expressive, family-friendly and visually dimensional. "
        "NO 2D, NO VECTOR, NO FLAT CARTOON, NO STICKER, NO EMOJI, NO CLIP-ART, NO WORKSHEET, "
        "NO POSTER, NO CEL-SHADED ILLUSTRATION, NO TEXT, NO LOGO, NO WATERMARK."
    )
    seed = 48100 + index * 97
    result = _zimage_client.predict(prompt, ZIMAGE_HEIGHT, ZIMAGE_WIDTH, ZIMAGE_STEPS, seed, False, api_name="/generate_image")
    source = Path(extract_image_path(result))
    if not source.is_file():
        raise FileNotFoundError(f"Z-Image output does not exist: {source}")
    shutil.copy2(source, output_path)


def _generate_local_anchor(story, scene, index, output_path):
    scene_image(story, scene, index, output_path)


def generate_cinematic_anchor(story, scene, index, output_path, reference_path=None):
    global _gemini_disabled_reason, _zimage_disabled_reason
    if GEMINI_ENABLED and _gemini_disabled_reason is None:
        try:
            print(f"[Scene {index + 1}/3] Trying Gemini cinematic CGI anchor...")
            _generate_gemini_anchor(story, scene, output_path, reference_path)
            return "gemini"
        except Exception as exc:
            message = str(exc).replace("\n", " ")
            _gemini_disabled_reason = message[:500]
            print("[Image fallback] Gemini unavailable; moving to free ZeroGPU image generation.")
            print(f"[Image fallback] Gemini reason: {message[:500]}")
    if ZIMAGE_ENABLED and _zimage_disabled_reason is None:
        try:
            print(f"[Scene {index + 1}/3] Generating free Z-Image-Turbo cinematic CGI anchor...")
            _generate_zimage_anchor(story, scene, index, output_path)
            return "z-image-turbo"
        except Exception as exc:
            message = str(exc).replace("\n", " ")
            _zimage_disabled_reason = message[:500]
            print("[Image fallback] Z-Image-Turbo unavailable.")
            print(f"[Image fallback] Z-Image reason: {message[:500]}")
    if CINEMATIC_ONLY:
        raise RuntimeError("No cinematic image provider is available; refusing the legacy flat 2D renderer.")
    print("[WARNING] Explicit emergency mode: using legacy local 2D renderer.")
    _generate_local_anchor(story, scene, index, output_path)
    return "local-emergency"


def make_clip(client, story, scene, index, character_reference):
    image_path = WORK / f"wan_10sec_scene_{index + 1}.png"
    clip_path = WORK / f"wan_10sec_scene_{index + 1}.mp4"
    print(f"[Scene {index + 1}/3] Creating cinematic CGI anchor image...")
    reference = character_reference if index > 0 and character_reference.is_file() else None
    source_type = generate_cinematic_anchor(story, scene, index, image_path, reference)
    print(f"[Scene {index + 1}/3] Anchor ready via {source_type} renderer.")
    if index == 0:
        shutil.copy2(image_path, character_reference)
    prompt = (
        "Premium theatrical 3D animated musical feature film. Preserve EXACT character identity, face, colors, clothing and proportions. "
        f"Character: {story.get('character', 'cute animated animal')}. Scene: {scene.get('visual', '')}. "
        f"Camera: {scene.get('camera', 'smooth cinematic tracking shot')}. "
        "Dimensional CGI, physically believable motion, stable anatomy and face, cinematic depth, volumetric lighting, "
        "subtle motion blur, optical bokeh, realistic shadows, polished feature-film rendering, joyful musical energy. "
        "Do not turn the scene into a simple 2D cartoon. No text, subtitles, logo or watermark."
    )[:1100]
    negative_prompt = (
        "flat vector art, 2D illustration, sticker, emoji, clip-art, worksheet style, simplistic shapes, flat fills, "
        "ink outlines, cel-shaded poster, blurry, low quality, distorted face, deformed body, extra limbs, missing limbs, "
        "bad anatomy, duplicate character, character morphing, face morphing, flicker, jitter, frame tearing, unstable clothing, "
        "unstable colors, text, letters, subtitles, logo, watermark, gray frame, noise"
    )
    print(f"[Scene {index + 1}/3] Generating {CLIP_SECONDS}s Wan 2.2 cinematic clip...")
    result = client.predict(handle_file(str(image_path)), prompt, 6, negative_prompt, CLIP_SECONDS, 1.0, 1.0, 1000 + index, False, api_name="/generate_video")
    source = Path(extract_video_path(result))
    if not source.is_file():
        raise FileNotFoundError(f"HF video does not exist: {source}")
    shutil.copy2(source, clip_path)
    return clip_path


def concat_and_trim(clips):
    concat_file = WORK / "wan_10sec_concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clips), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-t", str(FINAL_SECONDS), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)]
    print("Assembling the 10-second cinematic video...")
    subprocess.run(cmd, check=True)


def make_music(path):
    rate = 44100
    total = int(FINAL_SECONDS * rate)
    buf = [0.0] * total
    melody = [523.25, 659.25, 783.99, 659.25, 587.33, 698.46, 880.00, 698.46]
    bass = [261.63, 293.66, 329.63, 392.00]
    for step, freq in enumerate(melody * 2):
        start = step * 0.625
        a = int(start * rate); b = min(total, int((start + 0.48) * rate))
        for i in range(a, b):
            t = i / rate - start
            env = min(1.0, t / 0.025) * max(0.0, 1.0 - t / 0.48)
            buf[i] += 0.028 * math.sin(2 * math.pi * freq * t) * env
            buf[i] += 0.008 * math.sin(2 * math.pi * (freq * 2) * t) * env
    for bar, freq in enumerate(bass):
        start = bar * 2.5
        for i in range(int(start * rate), min(total, int((start + 2.1) * rate))):
            t = i / rate - start
            env = min(1.0, t / 0.04) * max(0.0, 1.0 - t / 2.1)
            buf[i] += 0.018 * math.sin(2 * math.pi * freq * t) * env
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        wf.writeframes(b"".join(int(max(-1.0, min(1.0, x)) * 32767).to_bytes(2, "little", signed=True) for x in buf))


async def make_voice(text, path):
    import edge_tts
    await edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate="+12%", pitch="+2Hz").save(str(path))


def add_rhyme_audio(video, story):
    music = WORK / "nursery_music.wav"
    voice = WORK / "nursery_rhyme_voice.mp3"
    make_music(music)
    rhyme = story.get("rhyme") or " ".join(scene.get("narration", "") for scene in story.get("scenes", [])[:3])
    print("🎵 Creating Hindi nursery-rhyme voice...")
    asyncio.run(make_voice(rhyme, voice))
    out = OUT.with_name(OUT.stem + "_av.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(video), "-i", str(music), "-i", str(voice),
        "-filter_complex", "[1:a]volume=0.22[m];[2:a]apad,atrim=0:10,volume=1.15[v];[m][v]amix=inputs=2:duration=longest:dropout_transition=0,loudnorm=I=-15.5:TP=-1.5:LRA=10[aout]",
        "-map", "0:v", "-map", "[aout]", "-t", str(FINAL_SECONDS), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
    ]
    subprocess.run(cmd, check=True)
    shutil.move(out, video)


def main():
    WORK.mkdir(exist_ok=True)
    history = load_history()
    is_rhyme = CONTENT_MODE in {"rhyme", "nursery_rhyme", "nursery-rhyme"}
    story = local_rhyme(history) if is_rhyme else local_story(history)
    scenes = story.get("scenes", [])[:3]
    if len(scenes) < 3:
        raise RuntimeError("The selected content must contain at least 3 scenes.")
    print(f"Content mode: {CONTENT_MODE}")
    print(f"Title: {story['title']}")
    print("Plan: 3 cinematic scenes x 3.5s, exact 10s final video.")
    print(f"HF_TOKEN configured: {'yes' if HF_TOKEN else 'no (anonymous ZeroGPU fallback)'}")
    client = Client(SPACE, token=HF_TOKEN)
    character_reference = WORK / "wan_cinematic_character_reference.png"
    clips = [make_clip(client, story, scene, i, character_reference) for i, scene in enumerate(scenes)]
    concat_and_trim(clips)
    if is_rhyme:
        add_rhyme_audio(OUT, story)
    subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "default=noprint_wrappers=1", str(OUT)], check=True)
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
