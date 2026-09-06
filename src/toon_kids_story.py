import os
import re
import json
import time
import asyncio
import subprocess
import base64
import secrets
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
# SETTINGS
# ============================================================

TEXT_MODEL = os.getenv(
    "GEMINI_TEXT_MODEL",
    "gemini-3.6-flash"
)

CLOUDFLARE_IMAGE_MODEL = (
    "@cf/black-forest-labs/flux-1-schnell"
)

RUN_SLOT = os.getenv(
    "RUN_SLOT",
    "manual"
)

# Energetic Hindi voice
TTS_RATE = os.getenv(
    "TTS_RATE",
    "+15%"
)

TTS_PITCH = os.getenv(
    "TTS_PITCH",
    "+2Hz"
)


# ============================================================
# UNLIMITED-STYLE RANDOM TOPIC ENGINE
# ============================================================

CHARACTERS = [
    "नन्हा खरगोश",
    "शरारती बंदर",
    "प्यारा हाथी",
    "चतुर गिलहरी",
    "नन्हा पिल्ला",
    "रंगीन तोता",
    "छोटी बिल्ली",
    "बहादुर चूहा",
    "नन्हा हिरन",
    "मजेदार भालू",
    "चंचल लोमड़ी",
    "छोटी चिड़िया",
    "नन्हा रोबोट",
    "दयालु कछुआ",
    "मुस्कुराती तितली",
    "नन्हा पेंगुइन",
    "जिज्ञासु बकरी",
    "छोटा ड्रैगन",
    "नटखट गिलहरी",
    "नन्ही मछली",
    "प्यारा पांडा",
    "छोटा जिराफ",
    "नन्हा घोड़ा",
    "मजेदार मेंढक",
    "छोटी मधुमक्खी",
    "नन्हा उल्लू",
    "चंचल बंदरिया",
    "प्यारा भेड़ का बच्चा",
    "नन्हा समुद्री घोड़ा",
    "छोटा कंगारू"
]

PLACES = [
    "जादुई जंगल",
    "रंगीन गाँव",
    "चमकता हुआ बगीचा",
    "बादलों का शहर",
    "समुद्र किनारा",
    "इंद्रधनुषी पहाड़",
    "रहस्यमयी तालाब",
    "खिलौनों का शहर",
    "चाँदनी वाला जंगल",
    "फूलों की घाटी",
    "सितारों की दुनिया",
    "मजेदार स्कूल",
    "जादुई बाजार",
    "बारिश वाला जंगल",
    "बर्फीली पहाड़ी",
    "गुब्बारों की दुनिया",
    "सतरंगी नदी",
    "छोटा सा खेत",
    "सूरजमुखी का बगीचा",
    "चॉकलेट की दुनिया",
    "बादलों के ऊपर का गाँव",
    "समुद्र के नीचे की दुनिया",
    "रंग-बिरंगी कैंडी की घाटी",
    "चमकते फूलों का जंगल",
    "जादुई रेलवे स्टेशन",
    "पतंगों का शहर",
    "संगीत वाला जंगल",
    "खिलखिलाते बादलों की घाटी",
    "रोबोटों का छोटा शहर",
    "चाँद के पास का बगीचा"
]

OBJECTS = [
    "चमकती चाबी",
    "रहस्यमयी डिब्बा",
    "उड़ने वाली पतंग",
    "जादुई घंटी",
    "सुनहरी गेंद",
    "रंग बदलने वाला छाता",
    "छोटी जादुई किताब",
    "चमकता सितारा",
    "बोलने वाला खिलौना",
    "अनोखी बोतल",
    "सतरंगी पंख",
    "गायब होने वाली टोपी",
    "जादुई घड़ी",
    "चमकता सिक्का",
    "छोटा खजाना",
    "उड़ता गुब्बारा",
    "रहस्यमयी नक्शा",
    "मुस्कुराता हुआ पौधा",
    "जादुई सीटी",
    "चॉकलेट का पेड़",
    "चमकदार पत्थर",
    "रंग बदलने वाला फूल",
    "बोलने वाला बैग",
    "उड़ने वाली किताब",
    "जादुई जूते",
    "सतरंगी छड़ी",
    "छोटा संगीत बॉक्स",
    "गायब होने वाला खिलौना",
    "चमकती हुई सीप",
    "जादुई पेंसिल"
]

TWISTS = [
    "जो अचानक बोलने लगता है",
    "जो रास्ता दिखाता है",
    "जो रंग बदलता है",
    "जिसे सब ढूँढ रहे हैं",
    "जो एक मजेदार राज छुपाता है",
    "जो दोस्ती की परीक्षा लेता है",
    "जिससे पूरा जंगल हैरान हो जाता है",
    "जो एक छोटी समस्या को बड़ा रोमांच बना देता है",
    "जो सिर्फ सच्चे दोस्त को दिखाई देता है",
    "जो अचानक गायब हो जाता है",
    "जो सबकी मदद मांगता है",
    "जिसका राज आखिर में खुलता है",
    "जो हँसते-हँसते सबको एक सीख देता है",
    "जिसे वापस सही जगह पहुँचाना है",
    "जो एक अनोखी दोस्ती की शुरुआत करता है",
    "जो हर बार नई पहेली देता है",
    "जो बहुत मजेदार निकलता है",
    "जो एक खोए दोस्त तक पहुँचाता है",
    "जो बारिश शुरू होते ही चमकने लगता है",
    "जो खुशी बाँटना सिखाता है",
    "जिससे एक मजेदार सरप्राइज मिलता है",
    "जो पूरी कहानी बदल देता है",
    "जिसके पीछे एक प्यारा सा रहस्य है",
    "जो सबको मिलकर काम करना सिखाता है",
    "जो एक छोटी गलती को शानदार एडवेंचर बना देता है",
    "जो अंत में सबको हँसा देता है"
]

ACTIONS = [
    "एक खोई चीज़ खोजने निकलता है",
    "अपने दोस्त की मदद करता है",
    "एक मजेदार पहेली हल करता है",
    "सबको एक साथ इकट्ठा करता है",
    "एक छोटी गलती को ठीक करता है",
    "एक अनोखी प्रतियोगिता में भाग लेता है",
    "एक रहस्यमयी रास्ते पर जाता है",
    "बारिश से पहले एक काम पूरा करता है",
    "एक नए दोस्त से मिलता है",
    "एक छोटी मुसीबत का मजेदार हल निकालता है",
    "एक सरप्राइज पार्टी बचाता है",
    "एक खोया हुआ खजाना ढूँढता है",
    "एक अजीब आवाज़ का राज पता करता है",
    "सबको हँसाने वाला खेल शुरू करता है",
    "एक जादुई चीज़ को सही जगह पहुँचाता है",
    "अपने डर पर काबू पाता है",
    "एक दोस्त के लिए सरप्राइज तैयार करता है",
    "एक रहस्यमयी दरवाजा खोलता है",
    "एक मजेदार रेस में शामिल होता है",
    "एक खोई हुई दोस्ती वापस लाता है",
    "एक बड़ी समस्या का छोटा सा हल ढूँढता है",
    "एक अजीब सपने का मतलब पता करता है",
    "सबके साथ मिलकर एक शानदार काम करता है",
    "एक अनोखे मेले में पहुँच जाता है",
    "एक रहस्यमयी आवाज़ का पीछा करता है"
]


# ============================================================
# HELPERS
# ============================================================

def norm(value):
    return re.sub(
        r"[^a-z0-9\u0900-\u097f]+",
        " ",
        str(value).lower()
    ).strip()


def load_history():

    try:

        data = json.loads(
            HISTORY.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):
            return data

    except Exception:
        pass

    return []


def save_history(history):

    HISTORY.write_text(
        json.dumps(
            history[-1000:],
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# RANDOM TOPIC
# ============================================================

def choose_topic():

    history = load_history()

    used = {
        norm(item)
        for item in history
    }

    # Generate many random combinations.
    # This creates millions of possible topics.
    for _ in range(100):

        character = secrets.choice(
            CHARACTERS
        )

        place = secrets.choice(
            PLACES
        )

        obj = secrets.choice(
            OBJECTS
        )

        action = secrets.choice(
            ACTIONS
        )

        twist = secrets.choice(
            TWISTS
        )

        topic = (
            f"{character} का रोमांच: "
            f"{place} में {obj}, "
            f"जहाँ वह {action}, "
            f"लेकिन {twist}।"
        )

        if norm(topic) not in used:

            history.append(topic)

            save_history(history)

            return topic

    # Extremely unlikely fallback.
    topic = (
        f"{secrets.choice(CHARACTERS)} का "
        f"नया जादुई एडवेंचर "
        f"{secrets.token_hex(8)}"
    )

    history.append(topic)

    save_history(history)

    return topic


# ============================================================
# QUOTA CHECK
# ============================================================

def is_quota_error(exc):

    text = str(exc).upper()

    keywords = [
        "QUOTA EXCEEDED",
        "GENERATE_CONTENT_FREE_TIER_REQUESTS",
        "GENERATEREQUESTSPERDAY",
        "RESOURCE_EXHAUSTED",
        "FREE TIER"
    ]

    return any(
        keyword in text
        for keyword in keywords
    )


# ============================================================
# GEMINI STORY GENERATION
# ============================================================

def generate_story(topic):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY is missing."
        )

    client = genai.Client(
        api_key=api_key
    )

    prompt = f"""
Create one ORIGINAL Hindi kids story for Toon Kids YouTube Shorts.

RANDOM TOPIC INSPIRATION:
{topic}

IMPORTANT:
Do NOT simply repeat the topic sentence.
Use it only as inspiration and create a completely fresh,
fun and original story.

Every generation must feel different.

TARGET AUDIENCE:
Children ages 4-10.

LANGUAGE:
Simple, natural Hindi.
Easy words.
Fun spoken storytelling style.

TOTAL NARRATION:
115-145 Hindi words.

EXACTLY 8 SCENES.

Each scene must contain:

- narration: 1-2 short spoken Hindi sentences
- text: maximum 8 Hindi words for on-screen text
- image_prompt: detailed visual prompt for the scene

VOICE STYLE:
Write narration that sounds energetic when spoken aloud.
Use short sentences.
Use natural excitement.
Use playful expressions.
Avoid long complicated sentences.
Avoid boring exposition.

STORY STRUCTURE:

Scene 1:
VERY STRONG curiosity hook.
Start with something surprising or funny.

Scene 2:
Introduce the character and situation quickly.

Scene 3:
Create a simple problem or mystery.

Scene 4:
Increase curiosity and excitement.

Scene 5:
Funny or emotional moment.

Scene 6:
Character tries to solve the problem.

Scene 7:
Big reveal / satisfying solution.

Scene 8:
Happy ending + simple memorable moral.

CHARACTER CONSISTENCY:

Use the SAME main character appearance
through every scene.

Create a detailed but concise character_bible.

The character_bible must specify:

- species
- age/look
- body shape
- face
- eye color
- fur/skin color
- clothes
- accessories
- distinctive features

IMAGE PROMPTS:

Every image_prompt must repeat the important
character appearance details.

Make images:

- cute
- colorful
- cinematic
- expressive
- child-friendly
- high quality
- 3D animated
- visually exciting

NO:
violence
horror
politics
adult themes
dangerous instructions
copyrighted characters
logos
brand names

TEXT:

On-screen text must be short,
exciting and easy for children.

Maximum 8 Hindi words per scene.

Use words like:
"अरे वाह!"
"ये क्या हुआ?"
"चलो देखते हैं!"
"ओह! ये कैसे?"
"मिल गया!"
"वाह! कमाल!"

Do not put written text inside image_prompt.

Return ONLY valid JSON.

Use this exact structure:

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

            print(
                f"Gemini story attempt "
                f"{attempt + 1}/3..."
            )

            response = client.models.generate_content(
                model=TEXT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=1.0,
                    response_mime_type="application/json"
                )
            )

            story = json.loads(
                response.text.strip()
            )

            scenes = story.get(
                "scenes",
                []
            )

            if len(scenes) != 8:

                raise ValueError(
                    "Story must contain exactly 8 scenes."
                )

            required = [
                "title",
                "hook",
                "character_bible",
                "moral"
            ]

            for key in required:

                if not story.get(key):

                    raise ValueError(
                        f"Story missing: {key}"
                    )

            for index, scene in enumerate(
                scenes,
                1
            ):

                if not scene.get("narration"):

                    raise ValueError(
                        f"Scene {index} missing narration."
                    )

                if not scene.get("text"):

                    raise ValueError(
                        f"Scene {index} missing text."
                    )

                if not scene.get("image_prompt"):

                    raise ValueError(
                        f"Scene {index} missing image_prompt."
                    )

            return story

        except Exception as exc:

            print(
                "Gemini story error:",
                str(exc)
            )

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
# CLOUDFLARE IMAGE GENERATION
# ============================================================

def generate_image(prompt, filename):

    account_id = os.environ.get(
        "CLOUDFLARE_ACCOUNT_ID"
    )

    api_token = os.environ.get(
        "CLOUDFLARE_API_TOKEN"
    )

    if not account_id:

        raise RuntimeError(
            "CLOUDFLARE_ACCOUNT_ID is missing."
        )

    if not api_token:

        raise RuntimeError(
            "CLOUDFLARE_API_TOKEN is missing."
        )

    url = (
        "https://api.cloudflare.com/client/v4/"
        f"accounts/{account_id}/ai/run/"
        f"{CLOUDFLARE_IMAGE_MODEL}"
    )

    # --------------------------------------------------------
    # Prompt length protection
    # --------------------------------------------------------

    source_prompt = str(
        prompt
    ).strip()

    if len(source_prompt) > 1800:

        source_prompt = (
            source_prompt[:1800]
        )

    full_prompt = f"""
Premium children's 3D animated story frame.

STYLE:
Cute high-quality 3D cartoon.
Colorful family animation.
Warm cinematic lighting.
Soft rounded shapes.
Friendly expressive faces.
Bright cheerful environment.
Appealing for children ages 4-10.

CHARACTER CONSISTENCY:
Keep the main character exactly consistent.

Same species.
Same face.
Same eye color.
Same fur or skin color.
Same clothes.
Same accessories.
Same body proportions.
Same overall design.

CHARACTER AND SCENE:
{source_prompt}

COMPOSITION:
Vertical portrait composition.
Main character large and clearly visible.
Main action in center.
Simple clean background.
Strong facial expression.
Clear storytelling.
Leave safe space at top and bottom.

IMAGE RULES:
Original characters only.
No copyrighted characters.
No logos.
No watermark.
No written words.
No captions.
No subtitles.
No speech bubbles.
No text inside image.
No UI.
"""

    full_prompt = full_prompt.strip()

    if len(full_prompt) > 2000:

        print(
            f"Prompt length {len(full_prompt)} chars. "
            "Reducing to 2000 chars."
        )

        full_prompt = (
            full_prompt[:2000]
        )

    print(
        "Cloudflare prompt length:",
        len(full_prompt)
    )

    # IMPORTANT:
    # Do NOT send seed.
    # Cloudflare endpoint rejected /seed.

    payload = {
        "prompt": full_prompt,
        "steps": 4
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

            # ------------------------------------------------
            # Rate limit
            # ------------------------------------------------

            if response.status_code == 429:

                print(
                    "Cloudflare rate limit."
                )

                if attempt == 3:

                    print(
                        "Cloudflare response:",
                        response.text[:2000]
                    )

                    raise RuntimeError(
                        "Cloudflare rate limit after "
                        "all retries."
                    )

                wait_seconds = (
                    15 * (attempt + 1)
                )

                print(
                    f"Waiting {wait_seconds}s..."
                )

                time.sleep(
                    wait_seconds
                )

                continue

            # ------------------------------------------------
            # Server errors
            # ------------------------------------------------

            if response.status_code >= 500:

                print(
                    "Cloudflare temporary server error:",
                    response.status_code
                )

                print(
                    response.text[:1000]
                )

                if attempt == 3:

                    raise RuntimeError(
                        "Cloudflare server error after "
                        "all retries."
                    )

                time.sleep(
                    10 * (attempt + 1)
                )

                continue

            # ------------------------------------------------
            # Client errors
            # ------------------------------------------------

            if response.status_code >= 400:

                print(
                    "Cloudflare HTTP error:",
                    response.status_code
                )

                print(
                    "Cloudflare API response:"
                )

                print(
                    response.text[:3000]
                )

                raise RuntimeError(
                    "Cloudflare image request failed: "
                    f"HTTP {response.status_code}"
                )

            # ------------------------------------------------
            # Parse response
            # ------------------------------------------------

            try:

                data = response.json()

            except Exception as exc:

                print(
                    "Cloudflare returned invalid JSON:"
                )

                print(
                    response.text[:3000]
                )

                raise RuntimeError(
                    "Invalid Cloudflare API response."
                ) from exc

            if not data.get("success"):

                errors = data.get(
                    "errors",
                    []
                )

                print(
                    "Cloudflare API errors:",
                    errors
                )

                raise RuntimeError(
                    "Cloudflare image generation failed: "
                    + str(errors)
                )

            result = data.get(
                "result",
                {}
            )

            image_b64 = result.get(
                "image"
            )

            if not image_b64:

                print(
                    "Cloudflare result:"
                )

                print(
                    str(result)[:3000]
                )

                raise RuntimeError(
                    "Cloudflare returned no image data."
                )

            # ------------------------------------------------
            # Remove data URI prefix
            # ------------------------------------------------

            if image_b64.startswith(
                "data:image"
            ):

                image_b64 = (
                    image_b64.split(
                        ",",
                        1
                    )[1]
                )

            # ------------------------------------------------
            # Decode image
            # ------------------------------------------------

            try:

                image_bytes = (
                    base64.b64decode(
                        image_b64
                    )
                )

            except Exception as exc:

                raise RuntimeError(
                    "Could not decode Cloudflare image."
                ) from exc

            output_path = Path(
                filename
            )

            output_path.write_bytes(
                image_bytes
            )

            if (
                not output_path.exists()
                or output_path.stat().st_size == 0
            ):

                raise RuntimeError(
                    "Generated image file is empty."
                )

            print(
                f"Image saved successfully: "
                f"{output_path}"
            )

            print(
                f"Image size: "
                f"{output_path.stat().st_size} bytes"
            )

            return output_path

        except requests.Timeout as exc:

            print(
                "Cloudflare request timed out."
            )

            if attempt == 3:

                raise RuntimeError(
                    "Cloudflare request timed out "
                    "after all retries."
                ) from exc

            time.sleep(
                10 * (attempt + 1)
            )

        except requests.ConnectionError as exc:

            print(
                "Cloudflare connection error."
            )

            if attempt == 3:

                raise RuntimeError(
                    "Cloudflare connection failed."
                ) from exc

            time.sleep(
                10 * (attempt + 1)
            )


# ============================================================
# TEXT TO SPEECH
# ============================================================

def tts(story):

    import edge_tts

    narration = " ".join(
        scene["narration"]
        for scene in story["scenes"]
    )

    text = (
        narration
        + " "
        + story["moral"]
    )

    output = (
        WORK / "voice.mp3"
    )

    async def make_voice():

        communicate = edge_tts.Communicate(
            text,
            "hi-IN-SwaraNeural",
            rate=TTS_RATE,
            pitch=TTS_PITCH
        )

        await communicate.save(
            str(output)
        )

    asyncio.run(
        make_voice()
    )

    if (
        not output.exists()
        or output.stat().st_size == 0
    ):

        raise RuntimeError(
            "Hindi voice file was not created."
        )

    print(
        "Voice created:",
        output
    )

    print(
        "Voice settings:",
        f"rate={TTS_RATE}, pitch={TTS_PITCH}"
    )

    return output


# ============================================================
# FFMPEG / FFPROBE
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
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )

    return float(
        result.stdout.strip()
    )


def run_command(command):

    print(
        "Running:",
        " ".join(
            str(x)
            for x in command
        )
    )

    subprocess.run(
        command,
        check=True
    )


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
# BUILD VIDEO
# ============================================================

def build_video(story, voice):

    images = []

    bible = str(
        story["character_bible"]
    )

    if len(bible) > 900:

        bible = bible[:900]

    # --------------------------------------------------------
    # Generate 8 images
    # --------------------------------------------------------

    for index, scene in enumerate(
        story["scenes"],
        1
    ):

        image_path = (
            WORK / f"scene_{index}.png"
        )

        image_prompt = (
            "CHARACTER BIBLE:\n"
            + bible
            + "\n\nSCENE:\n"
            + str(
                scene["image_prompt"]
            )
        )

        print(
            "=" * 60
        )

        print(
            f"Generating image {index}/8..."
        )

        generate_image(
            image_prompt,
            image_path
        )

        images.append(
            image_path
        )

    # --------------------------------------------------------
    # Voice duration
    # --------------------------------------------------------

    total_voice = (
        ffprobe_duration(
            voice
        )
    )

    print(
        "Voice duration:",
        round(total_voice, 2),
        "seconds"
    )

    # --------------------------------------------------------
    # Calculate scene durations
    # --------------------------------------------------------

    weights = []

    for scene in story["scenes"]:

        words = max(
            1,
            len(
                scene["narration"].split()
            )
        )

        weights.append(
            words
        )

    total_weight = sum(
        weights
    )

    durations = []

    for weight in weights:

        duration = max(
            3.5,
            total_voice
            * weight
            / total_weight
        )

        durations.append(
            duration
        )

    # Make total visual duration
    # match voice duration.

    visual_total = sum(
        durations
    )

    if visual_total < total_voice:

        difference = (
            total_voice
            - visual_total
        )

        durations[-1] += (
            difference
        )

    # --------------------------------------------------------
    # Create clips
    # --------------------------------------------------------

    clips = []

    for index, (
        image,
        scene,
        duration
    ) in enumerate(
        zip(
            images,
            story["scenes"],
            durations
        ),
        1
    ):

        clip = (
            WORK / f"clip_{index}.mp4"
        )

        text = esc(
            scene["text"]
        )

        frames = max(
            1,
            int(duration * 30)
        )

        # ----------------------------------------------------
        # Clean text overlay
        #
        # IMPORTANT:
        # No black box.
        # Only white text + shadow.
        # ----------------------------------------------------

        vf = (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "zoompan="
            "z='min(zoom+0.0008,1.08)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={frames}:"
            "s=1080x1920:"
            "fps=30,"
            f"drawtext=text='{text}':"
            "fontcolor=white:"
            "fontsize=58:"
            "fontfile="
            "/usr/share/fonts/truetype/noto/"
            "NotoSansDevanagari-Regular.ttf:"
            "x=(w-text_w)/2:"
            "y=h-text_h-190:"
            "shadowcolor=black@0.90:"
            "shadowx=3:"
            "shadowy=3"
        )

        print(
            f"Building video clip "
            f"{index}/8..."
        )

        run_command(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(image),
                "-t",
                str(duration),
                "-vf",
                vf,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                str(clip)
            ]
        )

        clips.append(
            clip
        )

    # --------------------------------------------------------
    # Concatenate clips
    # --------------------------------------------------------

    concat_file = (
        WORK / "concat.txt"
    )

    concat_file.write_text(
        "\n".join(
            f"file '{clip.as_posix()}'"
            for clip in clips
        ),
        encoding="utf-8"
    )

    silent_video = (
        WORK / "silent.mp4"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(silent_video)
        ]
    )

    # --------------------------------------------------------
    # Background music
    # --------------------------------------------------------

    music = (
        WORK / "music.wav"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:"
            "sample_rate=44100",
            "-t",
            "120",
            "-filter:a",
            "volume=0.025",
            str(music)
        ]
    )

    # --------------------------------------------------------
    # Mix voice + music
    # --------------------------------------------------------

    mixed_audio = (
        WORK / "mixed.m4a"
    )

    run_command(
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
            "LRA=11[voice];"
            "[1:a]"
            "volume=0.30[music];"
            "[voice][music]"
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
            str(mixed_audio)
        ]
    )

    # --------------------------------------------------------
    # Final video
    # --------------------------------------------------------

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(mixed_audio),
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
            str(OUT)
        ]
    )

    if (
        not OUT.exists()
        or OUT.stat().st_size == 0
    ):

        raise RuntimeError(
            "Final video was not created."
        )

    print(
        "FINAL VIDEO CREATED:",
        OUT
    )


# ============================================================
# YOUTUBE UPLOAD
# ============================================================

def upload_youtube():

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    required = [
        "YOUTUBE_REFRESH_TOKEN",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET"
    ]

    for key in required:

        if not os.environ.get(key):

            raise RuntimeError(
                f"{key} is missing."
            )

    credentials = Credentials(
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
        credentials=credentials
    )

    metadata = json.loads(
        META.read_text(
            encoding="utf-8"
        )
    )

    title = (
        metadata["title"][:95]
        + " #Shorts"
    )

    description = (
        metadata["hook"]
        + "\n\n"
        "🌈 Toon Kids पर रोज़ नई हिंदी कहानी!"
        "\n❤️ इस कहानी से आपको क्या सीख मिली?"
        "\n\n"
        "#shorts #toonkids #hindistory "
        "#kidsstory #moralstory #hindikahani"
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
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

    print(
        "Uploading video to YouTube..."
    )

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

    print(
        "=" * 60
    )

    print(
        "TOON KIDS AUTOMATION STARTED"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # Environment check
    # --------------------------------------------------------

    required_env = [
        "GEMINI_API_KEY",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID"
    ]

    for key in required_env:

        if not os.environ.get(key):

            raise RuntimeError(
                f"Required secret missing: {key}"
            )

    # --------------------------------------------------------
    # Choose random topic
    # --------------------------------------------------------

    topic = choose_topic()

    print(
        "Selected random topic:",
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

    metadata = {
        "title": story["title"],
        "hook": story["hook"],
        "moral": story["moral"],
        "topic": topic
    }

    META.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Hindi energetic voice
    # --------------------------------------------------------

    print(
        "Generating energetic Hindi voice..."
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

        upload_youtube()

    else:

        print(
            "YouTube upload disabled."
        )

    print(
        "=" * 60
    )

    print(
        "TOON KIDS AUTOMATION COMPLETED"
    )

    print(
        "=" * 60
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
