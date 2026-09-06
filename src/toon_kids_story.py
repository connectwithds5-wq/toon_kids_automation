import os
import re
import json
import time
import hashlib
import asyncio
import subprocess
import base64
from pathlib import Path
from datetime import datetime, timezone

import requests
from google import genai
from google.genai import types


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent

OUT = BASE / "toon_kids_short.mp4"
META = BASE / "story_metadata.json"
HISTORY = BASE / "story_history.json"
WORK = BASE / "work"

WORK.mkdir(exist_ok=True)


# ============================================================
# MODELS / SETTINGS
# ============================================================

TEXT_MODEL = os.getenv(
    "GEMINI_TEXT_MODEL",
    "gemini-3.6-flash"
)

CLOUDFLARE_IMAGE_MODEL = (
    "@cf/black-forest-labs/flux-1-schnell"
)

RUN_SLOT = os.getenv("RUN_SLOT", "manual")

TTS_RATE = os.getenv("TTS_RATE", "+5%")


# ============================================================
# TOPICS
# ============================================================

TOPICS = [
    "ईमानदार खरगोश और चमकदार डिब्बा",
    "प्यासा कौआ और छोटी सी सीख",
    "चतुर बंदर और लालची मगरमच्छ",
    "नन्ही चिड़िया का बड़ा हौसला",
    "शेर और छोटे चूहे की दोस्ती",
    "कछुआ जिसने हार नहीं मानी",
    "चींटी और बारिश का दिन",
    "जादुई पेड़ और सच्चा बच्चा",
    "गाँव का छोटा दीपक",
    "भूला हुआ खिलौना और नन्हा मालिक",
    "बिल्ली जिसने दोस्ती सीखी",
    "नन्हा हाथी और पानी का तालाब",
    "गिलहरी और खोया हुआ अखरोट",
    "सुनहरी मछली और दयालु बच्चा",
    "चाँद को पत्र लिखने वाली बच्ची",
    "बारिश में भीगता छोटा पिल्ला",
    "बगीचे का सबसे छोटा फूल",
    "नन्हा हिरन और जंगल का रास्ता",
    "झूठ बोलने वाला तोता",
    "मददगार मधुमक्खी",
    "गुस्सैल बादल और इंद्रधनुष",
    "प्यारा भालू और शहद का छत्ता",
    "नन्ही परी और खोई हुई घंटी",
    "चतुर चूहे का अनोखा उपाय",
    "पेड़ बचाने वाले बच्चों की टोली",
    "नन्हा रोबोट और उसका पहला दोस्त",
    "समुद्र किनारे मिली रहस्यमयी बोतल",
    "रात में चमकता छोटा तारा",
    "नन्ही बिल्ली और रंगीन पतंग",
    "दादी की पुरानी जादुई घड़ी",
]


# ============================================================
# HELPERS
# ============================================================

def norm(s):
    return re.sub(
        r"[^a-z0-9\u0900-\u097f]+",
        " ",
        str(s).lower()
    ).strip()


def load_history():
    try:
        d = json.loads(
            HISTORY.read_text(encoding="utf-8")
        )
        return d if isinstance(d, list) else []
    except Exception:
        return []


def save_history(h):
    HISTORY.write_text(
        json.dumps(
            h[-1000:],
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def choose_topic():
    history = load_history()

    used = {
        norm(x)
        for x in history
    }

    key = (
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        f":{RUN_SLOT}"
    )

    start = (
        int(
            hashlib.sha256(
                key.encode()
            ).hexdigest()[:8],
            16
        )
        % len(TOPICS)
    )

    for i in range(len(TOPICS)):
        topic = TOPICS[
            (start + i) % len(TOPICS)
        ]

        if norm(topic) not in used:
            history.append(topic)
            save_history(history)
            return topic

    topic = TOPICS[start]
    history.append(topic)
    save_history(history)

    return topic


def is_quota_error(exc):
    text = str(exc).upper()

    return any(
        item in text
        for item in [
            "QUOTA EXCEEDED",
            "GENERATE_CONTENT_FREE_TIER_REQUESTS",
            "GENERATEREQUESTSPERDAY",
            "RESOURCE_EXHAUSTED",
            "FREE TIER",
        ]
    )


# ============================================================
# GEMINI STORY GENERATION
# ============================================================

def generate_story(topic):

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"]
    )

    prompt = f"""
Create one ORIGINAL Hindi kids story for Toon Kids YouTube Shorts.

Topic: {topic}

Return ONLY valid JSON.

Age: 4-10.

Total narration:
115-145 Hindi words.

Exactly 8 scenes.

Each scene must contain:
- narration: 1-2 short spoken Hindi sentences
- text: maximum 8 Hindi words for on-screen text
- image_prompt: detailed visual prompt for a cute original 3D cartoon scene

Use the SAME main character appearance in every scene.

Include a strong curiosity hook in scene 1.

Happy, wholesome ending and one clear moral.

No violence, horror, politics, adult themes,
dangerous instructions, or copyrighted characters.

Use this exact JSON structure:

{{
  "title": "...",
  "hook": "...",
  "character_bible": "...",
  "scenes": [
    {{
      "narration": "...",
      "text": "...",
      "image_prompt": "..."
    }}
  ],
  "moral": "..."
}}
"""

    for attempt in range(3):

        try:

            response = client.models.generate_content(
                model=TEXT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    response_mime_type="application/json"
                )
            )

            story = json.loads(
                response.text.strip()
            )

            if len(story.get("scenes", [])) != 8:
                raise ValueError(
                    "Story did not contain exactly 8 scenes."
                )

            return story

        except Exception as exc:

            if is_quota_error(exc):
                raise RuntimeError(
                    "Gemini text quota exhausted."
                ) from exc

            if attempt == 2:
                raise

            time.sleep(
                10 * (attempt + 1)
            )


# ============================================================
# CLOUDFLARE FLUX IMAGE GENERATION
# ============================================================

def generate_image(prompt, filename):

    account_id = os.environ[
        "CLOUDFLARE_ACCOUNT_ID"
    ]

    api_token = os.environ[
        "CLOUDFLARE_API_TOKEN"
    ]

    url = (
        "https://api.cloudflare.com/client/v4/"
        f"accounts/{account_id}/ai/run/"
        f"{CLOUDFLARE_IMAGE_MODEL}"
    )

    full_prompt = f"""
Create a premium children's animated story image.

VISUAL STYLE:
Cute high-quality 3D cartoon.
Colorful.
Warm cinematic lighting.
Soft rounded shapes.
Friendly expressive faces.
Premium family-animation look.
Very appealing to children ages 4-10.

CHARACTER CONSISTENCY:
Keep the main character visually consistent.
Same species.
Same face.
Same eye color.
Same fur/skin color.
Same clothes.
Same accessories.
Same body proportions.
Same overall character design.

CHARACTER BIBLE:
{prompt}

COMPOSITION:
Portrait-oriented children's animation composition.
Main character large and clearly visible.
Important action in the center.
Clean uncluttered background.
Leave some safe space near top and bottom for
YouTube Shorts captions.

IMAGE RULES:
Original characters only.
No copyrighted characters.
No logos.
No watermark.
No written words.
No captions.
No subtitles.
No speech bubbles.
No text inside the image.
No UI elements.
"""


    payload = {
        "prompt": full_prompt,
        "steps": 4,
        "seed": int.from_bytes(
            os.urandom(4),
            "big"
        )
    }


    for attempt in range(4):

        try:

            print(
                f"Cloudflare image attempt "
                f"{attempt + 1}/4..."
            )

            response = requests.post(
                url,
                headers={
                    "Authorization":
                        f"Bearer {api_token}",
                    "Content-Type":
                        "application/json"
                },
                json=payload,
                timeout=180
            )


            # Rate limit
            if response.status_code == 429:

                if attempt == 3:
                    response.raise_for_status()

                print(
                    "Cloudflare rate limit. "
                    "Waiting before retry..."
                )

                time.sleep(
                    15 * (attempt + 1)
                )

                continue


            # Temporary server error
            if response.status_code >= 500:

                if attempt == 3:
                    response.raise_for_status()

                print(
                    "Cloudflare temporary server error."
                )

                time.sleep(
                    10 * (attempt + 1)
                )

                continue


            response.raise_for_status()


            data = response.json()


            if not data.get("success"):

                raise RuntimeError(
                    "Cloudflare image generation failed: "
                    + str(
                        data.get("errors")
                    )
                )


            result = data.get(
                "result",
                {}
            )


            image_b64 = result.get(
                "image"
            )


            if not image_b64:

                raise RuntimeError(
                    "Cloudflare returned no image data."
                )


            # Decode Base64 image
            image_bytes = base64.b64decode(
                image_b64
            )


            Path(filename).write_bytes(
                image_bytes
            )


            # Verify file
            if (
                not Path(filename).exists()
                or Path(filename).stat().st_size == 0
            ):
                raise RuntimeError(
                    "Generated image file is empty."
                )


            print(
                f"Image saved: {filename}"
            )

            return


        except requests.RequestException as exc:

            if attempt == 3:
                raise RuntimeError(
                    f"Cloudflare request failed: {exc}"
                ) from exc

            print(
                "Cloudflare request error. Retrying..."
            )

            time.sleep(
                10 * (attempt + 1)
            )


# ============================================================
# TEXT TO SPEECH
# ============================================================

def tts(story):

    import edge_tts

    text = (
        " ".join(
            scene["narration"]
            for scene in story["scenes"]
        )
        + " "
        + story["moral"]
    )

    output = WORK / "voice.mp3"


    async def make():

        await edge_tts.Communicate(
            text,
            "hi-IN-SwaraNeural",
            rate=TTS_RATE
        ).save(
            str(output)
        )


    asyncio.run(make())

    return output


# ============================================================
# FFPROBE
# ============================================================

def ffprobe_duration(path):

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True
    )

    return float(
        result.stdout.strip()
    )


# ============================================================
# FFMPEG TEXT ESCAPE
# ============================================================

def esc(text):

    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("\n", " ")
    )


# ============================================================
# RUN COMMAND
# ============================================================

def run(cmd):

    subprocess.run(
        cmd,
        check=True
    )


# ============================================================
# BUILD VIDEO
# ============================================================

def build_video(story, voice):

    images = []

    bible = story[
        "character_bible"
    ]


    # --------------------------------------------------------
    # Generate 8 images
    # --------------------------------------------------------

    for i, scene in enumerate(
        story["scenes"],
        1
    ):

        img = WORK / f"scene_{i}.jpg"

        image_prompt = (
            f"{bible}\n\n"
            f"Scene {i}: "
            f"{scene['image_prompt']}"
        )

        print(
            f"Generating image {i}/8..."
        )

        generate_image(
            image_prompt,
            img
        )

        images.append(img)


    # --------------------------------------------------------
    # Voice duration
    # --------------------------------------------------------

    total_voice = ffprobe_duration(
        voice
    )


    weights = []

    for scene in story["scenes"]:

        words = max(
            1,
            len(
                scene["narration"].split()
            )
        )

        weights.append(words)


    total_weight = sum(weights)


    # --------------------------------------------------------
    # Create clips
    # --------------------------------------------------------

    clips = []


    for i, (
        img,
        scene,
        weight
    ) in enumerate(
        zip(
            images,
            story["scenes"],
            weights
        ),
        1
    ):

        duration = max(
            3.5,
            total_voice
            * weight
            / total_weight
        )


        clip = (
            WORK
            / f"clip_{i}.mp4"
        )


        text = esc(
            scene["text"]
        )


        vf = (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "zoompan="
            "z='min(zoom+0.0008,1.08)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={int(duration * 30)}:"
            "s=1080x1920:"
            "fps=30,"
            f"drawtext=text='{text}':"
            "fontcolor=white:"
            "fontsize=58:"
            "fontfile="
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans.ttf:"
            "x=(w-text_w)/2:"
            "y=h-text_h-190:"
            "box=1:"
            "boxcolor=black@0.48:"
            "boxborderw=24"
        )


        run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(img),
                "-t",
                str(duration),
                "-vf",
                vf,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ]
        )


        clips.append(clip)


    # --------------------------------------------------------
    # Concatenate clips
    # --------------------------------------------------------

    concat = (
        WORK / "concat.txt"
    )

    concat.write_text(
        "\n".join(
            f"file '{x.as_posix()}'"
            for x in clips
        ),
        encoding="utf-8"
    )


    silent = (
        WORK / "silent.mp4"
    )


    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-c",
            "copy",
            str(silent),
        ]
    )


    # --------------------------------------------------------
    # Background music
    # --------------------------------------------------------

    music = (
        WORK / "music.wav"
    )


    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:"
            "sample_rate=44100",
            "-t",
            "90",
            "-filter:a",
            "volume=0.025",
            str(music),
        ]
    )


    # --------------------------------------------------------
    # Mix voice + music
    # --------------------------------------------------------

    mixed = (
        WORK / "mixed.m4a"
    )


    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(voice),
            "-i",
            str(music),
            "-filter_complex",
            "[0:a]"
            "loudnorm="
            "I=-16:"
            "TP=-1.5:"
            "LRA=11[v];"
            "[1:a]"
            "volume=0.30[m];"
            "[v][m]"
            "amix="
            "inputs=2:"
            "duration=first,"
            "loudnorm="
            "I=-14:"
            "TP=-1:"
            "LRA=10",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(mixed),
        ]
    )


    # --------------------------------------------------------
    # Final video
    # --------------------------------------------------------

    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent),
            "-i",
            str(mixed),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(OUT),
        ]
    )


# ============================================================
# YOUTUBE UPLOAD
# ============================================================

def upload_youtube():

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials


    creds = Credentials(
        None,
        refresh_token=os.environ[
            "YOUTUBE_REFRESH_TOKEN"
        ],
        token_uri=(
            "https://oauth2.googleapis.com/token"
        ),
        client_id=os.environ[
            "YOUTUBE_CLIENT_ID"
        ],
        client_secret=os.environ[
            "YOUTUBE_CLIENT_SECRET"
        ],
        scopes=[
            "https://www.googleapis.com/auth/"
            "youtube.upload"
        ]
    )


    youtube = build(
        "youtube",
        "v3",
        credentials=creds
    )


    data = json.loads(
        META.read_text(
            encoding="utf-8"
        )
    )


    body = {
        "snippet": {
            "title": (
                data["title"][:95]
                + " #Shorts"
            ),

            "description": (
                data["hook"]
                + "\n\n"
                "🌈 Toon Kids पर रोज़ नई हिंदी कहानी!"
                "\n❤️ इस कहानी से आपको क्या सीख मिली?"
                "\n\n"
                "#shorts #toonkids #hindistory "
                "#kidsstory #moralstory #hindikahani"
            ),

            "tags": [
                "toon kids",
                "hindi kids story",
                "kids story",
                "hindi kahani",
                "moral story",
                "bachon ki kahani",
                "kids shorts",
                "bedtime story"
            ],

            "categoryId": "27"
        },

        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": True
        }
    }


    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(
            str(OUT),
            mimetype="video/mp4",
            resumable=True
        )
    )


    response = request.execute()


    print(
        "YouTube upload successful!"
    )

    print(
        "Video ID:",
        response.get("id")
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("TOON KIDS AUTOMATION STARTED")
    print("=" * 60)


    # --------------------------------------------------------
    # Choose topic
    # --------------------------------------------------------

    topic = choose_topic()

    print(
        "Selected topic:",
        topic
    )


    # --------------------------------------------------------
    # Generate story
    # --------------------------------------------------------

    print(
        "Generating Hindi story..."
    )

    story = generate_story(
        topic
    )


    print(
        "Story generated:",
        story["title"]
    )


    # --------------------------------------------------------
    # Save metadata
    # --------------------------------------------------------

    META.write_text(
        json.dumps(
            {
                "title": story["title"],
                "hook": story["hook"],
                "moral": story["moral"],
                "topic": topic
            },
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


    # --------------------------------------------------------
    # Generate Hindi voice
    # --------------------------------------------------------

    print(
        "Generating Hindi voice..."
    )

    voice = tts(
        story
    )


    # --------------------------------------------------------
    # Build video
    # --------------------------------------------------------

    print(
        "Building video..."
    )

    build_video(
        story,
        voice
    )


    if not OUT.exists():
        raise RuntimeError(
            "Final video was not created."
        )


    print(
        "Video created:",
        OUT
    )


    # --------------------------------------------------------
    # Upload
    # --------------------------------------------------------

    upload_enabled = (
        os.getenv(
            "UPLOAD_YOUTUBE",
            "true"
        ).lower()
        == "true"
    )


    if upload_enabled:

        print(
            "Uploading to YouTube..."
        )

        upload_youtube()

    else:

        print(
            "YouTube upload disabled."
        )


    print("=" * 60)
    print("TOON KIDS AUTOMATION COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
