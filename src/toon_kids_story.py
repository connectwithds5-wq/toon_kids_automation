import os
import re
import json
import time
import hashlib
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timezone

from google import genai
from google.genai import types

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_short.mp4"
META = BASE / "story_metadata.json"
HISTORY = BASE / "story_history.json"
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
RUN_SLOT = os.getenv("RUN_SLOT", "manual")
TTS_RATE = os.getenv("TTS_RATE", "+5%")

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

def norm(s):
    return re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", str(s).lower()).strip()

def load_history():
    try:
        d = json.loads(HISTORY.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []

def save_history(h):
    HISTORY.write_text(json.dumps(h[-1000:], ensure_ascii=False, indent=2), encoding="utf-8")

def choose_topic():
    h = load_history()
    used = {norm(x) for x in h}
    key = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}:{RUN_SLOT}"
    start = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(TOPICS)
    for i in range(len(TOPICS)):
        t = TOPICS[(start + i) % len(TOPICS)]
        if norm(t) not in used:
            h.append(t)
            save_history(h)
            return t
    t = TOPICS[start]
    h.append(t)
    save_history(h)
    return t

def is_quota_error(exc):
    s = str(exc).upper()
    return any(x in s for x in [
        "QUOTA EXCEEDED", "GENERATE_CONTENT_FREE_TIER_REQUESTS",
        "GENERATEREQUESTSPERDAY", "RESOURCE_EXHAUSTED", "FREE TIER"
    ])

def generate_story(topic):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = f"""
Create one ORIGINAL Hindi kids story for Toon Kids YouTube Shorts.

Topic: {topic}

Return ONLY valid JSON.
Age: 4-10.
Total narration: 115-145 Hindi words.
Exactly 8 scenes.
Each scene:
- narration: 1-2 short spoken Hindi sentences
- text: maximum 8 Hindi words for on-screen text
- image_prompt: detailed visual prompt for a cute original 3D cartoon scene

Use the SAME main character appearance in every scene.
Include a strong curiosity hook in scene 1.
Happy, wholesome ending and one clear moral.
No violence, horror, politics, adult themes, dangerous instructions, or copyrighted characters.

Use this exact JSON:
{{
  "title": "...",
  "hook": "...",
  "character_bible": "...",
  "scenes": [
    {{"narration":"...","text":"...","image_prompt":"..."}}
  ],
  "moral":"..."
}}
"""
    for attempt in range(3):
        try:
            r = client.models.generate_content(
                model=TEXT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    response_mime_type="application/json"
                )
            )
            d = json.loads(r.text.strip())
            if len(d.get("scenes", [])) != 8:
                raise ValueError("Story did not contain exactly 8 scenes.")
            return d
        except Exception as e:
            if is_quota_error(e):
                raise RuntimeError("Gemini text quota exhausted. Stopping without quota retries.") from e
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))

def generate_image(client, prompt, filename):
    full_prompt = f"""
Create a vertical 9:16 image for a children's animated story.
Style: premium cute 3D cartoon, colorful, cinematic soft lighting, expressive friendly animal characters,
large readable facial expressions, polished family-animation look, original characters, no logos, no watermark.
Keep the character design consistent with this character bible:
{prompt}
Do not place captions, subtitles, speech bubbles, or written words inside the image.
Compose the important characters in the center-safe area for a 9:16 YouTube Short.
"""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio="9:16"
        )
    )
)
for part in response.parts:
    if part.inline_data is not None:
        part.as_image().save(filename)
        return
            raise RuntimeError("Image model returned no image.")
        except Exception as e:
            if is_quota_error(e):
                raise RuntimeError("Gemini image quota exhausted. Stopping.") from e
            if attempt == 2:
                raise
            time.sleep(8 * (attempt + 1))

def tts(story):
    import edge_tts
    text = " ".join(s["narration"] for s in story["scenes"]) + " " + story["moral"]
    out = WORK / "voice.mp3"

    async def make():
        await edge_tts.Communicate(
            text,
            "hi-IN-SwaraNeural",
            rate=TTS_RATE
        ).save(str(out))

    asyncio.run(make())
    return out

def ffprobe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True
    )
    return float(r.stdout.strip())

def esc(text):
    return (str(text).replace("\\", "\\\\").replace(":", "\\:")
            .replace("'", "\\'").replace("%", "\\%").replace("\n", " "))

def run(cmd):
    subprocess.run(cmd, check=True)

def build_video(story, voice):
    images = []
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    bible = story["character_bible"]

    for i, scene in enumerate(story["scenes"], 1):
        img = WORK / f"scene_{i}.png"
        image_prompt = f"{bible}\n\nScene {i}: {scene['image_prompt']}"
        print(f"Generating image {i}/8...")
        generate_image(client, image_prompt, img)
        images.append(img)

    total_voice = ffprobe_duration(voice)
    weights = []
    for scene in story["scenes"]:
        words = max(1, len(scene["narration"].split()))
        weights.append(words)
    total_weight = sum(weights)

    clips = []
    for i, (img, scene, weight) in enumerate(zip(images, story["scenes"], weights), 1):
        duration = max(3.5, total_voice * weight / total_weight)
        clip = WORK / f"clip_{i}.mp4"
        text = esc(scene["text"])
        vf = (
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"zoompan=z='min(zoom+0.0008,1.08)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={int(duration*30)}:s=1080x1920:fps=30,"
            f"drawtext=text='{text}':fontcolor=white:fontsize=58:"
            f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
            f"x=(w-text_w)/2:y=h-text_h-190:"
            f"box=1:boxcolor=black@0.48:boxborderw=24"
        )
        run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img),
            "-t", str(duration), "-vf", vf,
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)
        ])
        clips.append(clip)

    concat = WORK / "concat.txt"
    concat.write_text("\n".join(f"file '{x.as_posix()}'" for x in clips), encoding="utf-8")
    silent = WORK / "silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", str(silent)])

    music = WORK / "music.wav"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i",
         "sine=frequency=330:sample_rate=44100", "-t", "90",
         "-filter:a", "volume=0.025", str(music)])

    mixed = WORK / "mixed.m4a"
    run(["ffmpeg", "-y", "-i", str(voice), "-i", str(music),
         "-filter_complex",
         "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[v];"
         "[1:a]volume=0.30[m];"
         "[v][m]amix=inputs=2:duration=first,loudnorm=I=-14:TP=-1:LRA=10",
         "-c:a", "aac", "-b:a", "128k", str(mixed)])

    run(["ffmpeg", "-y", "-i", str(silent), "-i", str(mixed),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
         "-shortest", str(OUT)])

def upload_youtube():
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    creds = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    youtube = build("youtube", "v3", credentials=creds)
    data = json.loads(META.read_text(encoding="utf-8"))

    body = {
        "snippet": {
            "title": data["title"][:95] + " #Shorts",
            "description": (
                data["hook"] +
                "\n\n🌈 Toon Kids पर रोज़ नई हिंदी कहानी!"
                "\n❤️ इस कहानी से आपको क्या सीख मिली?"
                "\n\n#shorts #toonkids #hindistory #kidsstory #moralstory #hindikahani"
            ),
            "tags": [
                "toon kids", "hindi kids story", "kids story",
                "hindi kahani", "moral story", "bachon ki kahani",
                "kids shorts", "bedtime story"
            ],
            "categoryId": "27"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": True
        }
    }

    req = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(OUT), mimetype="video/mp4", resumable=True)
    )
    result = req.execute()
    print("YouTube upload complete:", result.get("id"))

def main():
    print("=== TOON KIDS AI STORY ===")
    topic = choose_topic()
    print("Topic:", topic)

    story = generate_story(topic)
    META.write_text(json.dumps({
        "topic": topic,
        **story,
        "created_at": datetime.now(timezone.utc).isoformat()
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    voice = tts(story)
    build_video(story, voice)

    if os.getenv("UPLOAD_YOUTUBE", "true").lower() == "true":
        upload_youtube()

    print("DONE:", OUT)

if __name__ == "__main__":
    main()
