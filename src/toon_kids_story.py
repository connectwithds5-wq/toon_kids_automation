import os
import json
import time
import asyncio
import hashlib
import secrets
import random
import subprocess
from pathlib import Path
from difflib import SequenceMatcher

from google import genai
from google.genai import types
import edge_tts
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# TOON KIDS — FREE / NO VIDEO-API STORY ENGINE
# Gemini text (with local fallback) -> vector cartoon scenes
# -> FFmpeg motion -> Hindi Edge TTS -> YouTube Shorts
# No Veo, no Cloudflare video, no GPU/video-generation quota.
# ============================================================

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_short.mp4"
META = BASE / "story_metadata.json"
HISTORY = BASE / "story_history.json"
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")
FALLBACK_TEXT_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
TTS_RATE = os.getenv("TTS_RATE", "+8%")
RUN_SLOT = os.getenv("RUN_SLOT", "manual")
UPLOAD_YOUTUBE = os.getenv("UPLOAD_YOUTUBE", "true").lower() == "true"
SCENE_COUNT = 7
SCENE_SECONDS = 8
FPS = 30
WIDTH = 1080
HEIGHT = 1920

CHARACTERS = [
    "छोटा खरगोश", "नन्हा हाथी", "प्यारा पिल्ला", "छोटी गिलहरी", "मजेदार बंदर",
    "नन्हा पांडा", "छोटा कछुआ", "प्यारी बिल्ली", "नन्हा हिरन", "छोटा तोता",
    "मजेदार पेंगुइन", "नन्हा भालू", "छोटी लोमड़ी", "प्यारा जिराफ"
]
PLACES = [
    "जादुई जंगल", "रंगीन गाँव", "चमकता बगीचा", "बादलों का शहर", "मजेदार स्कूल",
    "इंद्रधनुषी पहाड़", "सतरंगी नदी", "खिलौनों का शहर", "फूलों की घाटी", "जादुई बाजार"
]
OBJECTS = [
    "चमकती चाबी", "जादुई घंटी", "उड़ने वाली पतंग", "सुनहरी गेंद", "रहस्यमयी नक्शा",
    "जादुई किताब", "चमकता सितारा", "रंग बदलने वाला फूल", "संगीत बॉक्स", "जादुई पेंसिल"
]

LOCAL_STORIES = [
    {
        "title": "खरगोश की चमकती चाबी",
        "topic": "छोटा खरगोश जादुई जंगल में चमकती चाबी ढूँढता है और दोस्तों की मदद से उसका रहस्य समझता है।",
        "moral": "मिलकर कोशिश करने से मुश्किल काम आसान हो जाता है।",
        "character": "छोटा सफेद खरगोश, गुलाबी कान, नीली छोटी जैकेट, गोल प्यारी आँखें",
        "scenes": [
            {"narration":"छोटा खरगोश जंगल में खेलते खेलते एक चमकती चाबी देखता है।", "visual":"खरगोश चमकती चाबी देखकर खुशी से उछलता है।", "camera":"gentle push in"},
            {"narration":"वह चाबी उठाता है, लेकिन पास में कोई ताला दिखाई नहीं देता।", "visual":"खरगोश चाबी को ध्यान से देखता और आसपास खोजता है।", "camera":"slow pan right"},
            {"narration":"तभी उसकी गिलहरी दोस्त आती है और दोनों मिलकर रास्ता खोजते हैं।", "visual":"खरगोश और गिलहरी दोस्ताना अंदाज में साथ चलते हैं।", "camera":"gentle tracking"},
            {"narration":"उन्हें रंग-बिरंगे फूलों के पीछे एक छोटा सुनहरा दरवाजा मिलता है।", "visual":"दोनों फूलों के पीछे छिपा छोटा सुनहरा दरवाजा खोज लेते हैं।", "camera":"slow reveal"},
            {"narration":"खरगोश चाबी लगाता है और दरवाजा खुशी से खुल जाता है।", "visual":"खरगोश चमकती चाबी घुमाता है और दरवाजा रोशनी के साथ खुलता है।", "camera":"push in"},
            {"narration":"अंदर खिलौनों की टोकरी होती है, जिसे दोनों दोस्तों के लिए रखा गया था।", "visual":"दोनों दोस्त रंगीन खिलौनों की टोकरी देखकर बहुत खुश होते हैं।", "camera":"gentle zoom out"},
            {"narration":"खरगोश मुस्कुराकर कहता है, मिलकर कोशिश करने से हर काम आसान होता है।", "visual":"खरगोश और गिलहरी खिलौनों के साथ खुशी से हाथ हिलाते हैं।", "camera":"gentle push in"}
        ]
    },
    {
        "title": "नन्हे हाथी की उड़ती पतंग",
        "topic": "नन्हा हाथी रंगीन मैदान में पतंग उड़ाना सीखता है और दोस्तों की मदद से उसे आसमान तक पहुँचाता है।",
        "moral": "दोस्तों की मदद से नई चीजें सीखना मजेदार होता है।",
        "character": "नन्हा नीला हाथी, पीली टोपी, लाल स्कार्फ, बड़ी चमकदार आँखें",
        "scenes": [
            {"narration":"नन्हा हाथी मैदान में एक रंगीन पतंग लेकर बहुत उत्साहित होता है।", "visual":"हाथी रंगीन पतंग पकड़कर खुशी से मैदान में दौड़ता है।", "camera":"gentle push in"},
            {"narration":"वह पतंग उड़ाता है, लेकिन पतंग बार बार नीचे आ जाती है।", "visual":"पतंग थोड़ी ऊपर जाकर फिर नीचे आती है और हाथी हँसता है।", "camera":"slow pan left"},
            {"narration":"उसका छोटा दोस्त उसे सही दिशा में हवा पकड़ना सिखाता है।", "visual":"दो दोस्त मिलकर पतंग की डोरी और हवा की दिशा देखते हैं।", "camera":"gentle tracking"},
            {"narration":"हाथी फिर दौड़ता है और पतंग धीरे धीरे ऊपर जाने लगती है।", "visual":"हाथी दौड़ते हुए पतंग को आसमान की ओर उठाता है।", "camera":"tilt up"},
            {"narration":"कुछ ही पल में पतंग बादलों के पास सुंदर गोल चक्कर लगाती है।", "visual":"रंगीन पतंग नीले आसमान में बादलों के बीच घूमती है।", "camera":"slow zoom out"},
            {"narration":"हाथी खुशी से अपनी सूंड उठाकर दोस्तों को धन्यवाद देता है।", "visual":"हाथी सूंड उठाकर दोस्तों के साथ खुशी मनाता है।", "camera":"gentle push in"},
            {"narration":"वह सीखता है कि दोस्तों की मदद से सीखना कितना मजेदार होता है।", "visual":"सभी दोस्त पतंग के नीचे मुस्कुराते हुए साथ खड़े हैं।", "camera":"gentle zoom out"}
        ]
    }
]


def load_history():
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(history):
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def norm(s):
    return " ".join(str(s).lower().split())


def story_text(story):
    parts = [story.get("title", ""), story.get("moral", ""), story.get("topic", "")]
    for scene in story.get("scenes", []):
        parts.extend([scene.get("narration", ""), scene.get("visual", "")])
    return " ".join(parts)


def similar(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def is_duplicate(story, history):
    current = story_text(story)
    title = story.get("title", "")
    fp = hashlib.sha256(norm(current).encode("utf-8")).hexdigest()
    for item in history:
        if isinstance(item, str):
            old_text, old_title = item, ""
        else:
            old_text = item.get("story_text", item.get("topic", ""))
            old_title = item.get("title", "")
            if item.get("fingerprint") == fp:
                return True
        if title and old_title and similar(title, old_title) >= 0.84:
            return True
        if old_text and similar(current, old_text) >= 0.78:
            return True
    return False


def choose_topic(history):
    used = {norm(x if isinstance(x, str) else x.get("topic", "")) for x in history}
    for _ in range(200):
        c = secrets.choice(CHARACTERS)
        p = secrets.choice(PLACES)
        o = secrets.choice(OBJECTS)
        topic = f"{c} का मजेदार रोमांच: {p} में {o} मिलने की कहानी, जिसमें एक छोटी समस्या, मजेदार खोज और प्यारा सरप्राइज हो।"
        if norm(topic) not in used:
            return topic
    return f"एक बिल्कुल नई बच्चों की कहानी {secrets.token_hex(6)}"


def make_story(client, topic, history):
    history_titles = []
    for item in history[-25:]:
        if isinstance(item, dict) and item.get("title"):
            history_titles.append(item["title"])
        elif isinstance(item, str):
            history_titles.append(item[:100])

    prompt = f"""
तुम एक expert Hindi preschool YouTube Shorts storyteller हो।
एक बिल्कुल नई, मजेदार, प्यारी और आसानी से समझ आने वाली कहानी बनाओ।
TOPIC SEED: {topic}
पुरानी कहानियों/टाइटल से बचो: {json.dumps(history_titles, ensure_ascii=False)}

STRICT OUTPUT: केवल valid JSON, कोई markdown नहीं।
Schema:
{{
  "title": "छोटा catchy Hindi title",
  "topic": "one-line story topic",
  "moral": "एक बहुत छोटा positive lesson",
  "character": "मुख्य character का पूरा fixed description",
  "scenes": [
    {{"narration":"12-18 सरल Hindi words", "visual":"clear visual action", "camera":"camera direction"}}
  ]
}}

Rules:
- Exactly {SCENE_COUNT} scenes.
- हर scene लगभग 8 seconds के narration के लिए हो; narration 12-18 सरल Hindi words.
- Scene 1 से 7 तक कहानी naturally आगे बढ़े और scene 7 में प्यारा ending + moral हो।
- Same main character, same appearance, same outfit पूरे video में।
- Preschool-friendly, colorful, funny, wholesome.
- No scary violence, weapons, horror or sad ending.
"""

    last_error = None
    for model in [TEXT_MODEL, FALLBACK_TEXT_MODEL]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            scenes = data.get("scenes", [])
            if len(scenes) != SCENE_COUNT:
                raise ValueError(f"Expected {SCENE_COUNT} scenes, got {len(scenes)}")
            data["character"] = str(data.get("character", "प्यारा cartoon animal"))
            data["moral"] = str(data.get("moral", "मिल-जुलकर मदद करना सबसे अच्छा है।"))
            return data
        except Exception as exc:
            last_error = exc
            print(f"⚠️ Story model {model} failed: {exc}")
            time.sleep(1)
    raise RuntimeError(f"Story generation failed: {last_error}")


def local_story(history):
    candidates = [s for s in LOCAL_STORIES if not is_duplicate(s, history)]
    if not candidates:
        # Create a fresh variant from the first template without needing an API.
        base = LOCAL_STORIES[0]
        variant = json.loads(json.dumps(base, ensure_ascii=False))
        variant["title"] = "खरगोश और दोस्तों का नया सरप्राइज"
        variant["topic"] = "खरगोश और उसके दोस्त एक नए रंगीन सरप्राइज की खोज करते हैं।"
        return variant
    return secrets.choice(candidates)


# ---------------------- LOCAL CARTOON ART ----------------------

def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf" if bold else "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_character(draw, name, cx, cy, scale=1.0, happy=True):
    n = str(name)
    # Fixed palette by animal type; the same mapping is reused for every scene.
    if "象" in n or "हाथी" in n:
        body, ear, accent = "#9ED7F5", "#78B8DD", "#FFD84D"
        head_r = 135
        draw.ellipse((cx-head_r, cy-head_r, cx+head_r, cy+head_r), fill=body, outline="#4D91B8", width=7)
        draw.ellipse((cx-175, cy-95, cx-95, cy+75), fill=ear, outline="#4D91B8", width=6)
        draw.ellipse((cx+95, cy-95, cx+175, cy+75), fill=ear, outline="#4D91B8", width=6)
        draw.rounded_rectangle((cx-35, cy+30, cx+35, cy+170), radius=35, fill=body, outline="#4D91B8", width=6)
    elif "पांडा" in n:
        body, ear, accent = "#F8F8F8", "#30343B", "#E85C75"
        head_r = 135
        draw.ellipse((cx-head_r, cy-head_r, cx+head_r, cy+head_r), fill=body, outline="#30343B", width=7)
        draw.ellipse((cx-120, cy-150, cx-40, cy-70), fill=ear)
        draw.ellipse((cx+40, cy-150, cx+120, cy-70), fill=ear)
        draw.ellipse((cx-105, cy-30, cx-35, cy+55), fill="#30343B")
        draw.ellipse((cx+35, cy-30, cx+105, cy+55), fill="#30343B")
    elif "लोमड़ी" in n or "गिलहरी" in n:
        body, ear, accent = "#F39A4A", "#E9792D", "#FFD84D"
        head_r = 130
        draw.ellipse((cx-head_r, cy-head_r, cx+head_r, cy+head_r), fill=body, outline="#B85E25", width=7)
        draw.polygon([(cx-105,cy-80),(cx-150,cy-210),(cx-30,cy-120)], fill=ear, outline="#B85E25")
        draw.polygon([(cx+105,cy-80),(cx+150,cy-210),(cx+30,cy-120)], fill=ear, outline="#B85E25")
    elif "कछुआ" in n:
        body, ear, accent = "#74C98C", "#4AA86A", "#F4C95D"
        draw.ellipse((cx-170,cy-115,cx+170,cy+115), fill=accent, outline="#4A8D60", width=8)
        draw.ellipse((cx-115,cy-125,cx+115,cy+125), fill=body, outline="#4A8D60", width=7)
        draw.ellipse((cx+85,cy-65,cx+170,cy+20), fill=body, outline="#4A8D60", width=6)
    elif "पेंगुइन" in n:
        body, ear, accent = "#384B66", "#FFFFFF", "#F6B64A"
        draw.ellipse((cx-135,cy-180,cx+135,cy+190), fill=body, outline="#263448", width=7)
        draw.ellipse((cx-95,cy-105,cx+95,cy+115), fill=ear)
        draw.polygon([(cx-35,cy-5),(cx+35,cy-5),(cx,cy+50)], fill=accent)
    elif "जिराफ" in n or "हिरन" in n:
        body, ear, accent = "#E8B85C", "#C98B35", "#7C5A32"
        draw.ellipse((cx-125,cy-140,cx+125,cy+130), fill=body, outline="#A9752C", width=7)
        draw.ellipse((cx-150,cy-155,cx-70,cy-75), fill=ear, outline="#A9752C", width=6)
        draw.ellipse((cx+70,cy-155,cx+150,cy-75), fill=ear, outline="#A9752C", width=6)
        for dx, dy in [(-65,-30),(45,-55),(-25,50),(65,55)]:
            draw.ellipse((cx+dx-20,cy+dy-20,cx+dx+20,cy+dy+20), fill=accent)
    else:
        body, ear, accent = "#F7F7F7", "#F0A8B8", "#6FA8FF"
        head_r = 130
        draw.ellipse((cx-head_r, cy-head_r, cx+head_r, cy+head_r), fill=body, outline="#A8A8A8", width=7)
        draw.polygon([(cx-95,cy-75),(cx-145,cy-230),(cx-25,cy-125)], fill=ear, outline="#A87888")
        draw.polygon([(cx+95,cy-75),(cx+145,cy-230),(cx+25,cy-125)], fill=ear, outline="#A87888")

    # Eyes and face
    eye_y = cy - 25
    for ex in (cx - 48, cx + 48):
        draw.ellipse((ex-18, eye_y-28, ex+18, eye_y+28), fill="#1E2630")
        draw.ellipse((ex-7, eye_y-19, ex+3, eye_y-9), fill="white")
    if happy:
        draw.arc((cx-55, cy+5, cx+55, cy+85), 10, 170, fill="#7A3F4A", width=8)
    else:
        draw.arc((cx-50, cy+35, cx+50, cy+80), 190, 350, fill="#7A3F4A", width=7)
    # simple outfit / accessory keeps continuity recognizable
    rounded(draw, (cx-115, cy+115, cx+115, cy+245), 35, accent)


def draw_object(draw, obj, cx, cy, scale=1.0):
    o = str(obj)
    if "चाबी" in o:
        draw.ellipse((cx-55,cy-55,cx+55,cy+55), outline="#FFD84D", width=22)
        draw.line((cx+45,cy,cx+190,cy), fill="#FFD84D", width=22)
        draw.line((cx+150,cy,cx+150,cy+45), fill="#FFD84D", width=22)
    elif "घंटी" in o:
        draw.polygon([(cx-110,cy-45),(cx+110,cy-45),(cx+70,cy+90),(cx-70,cy+90)], fill="#FFD84D", outline="#C89C22")
        draw.ellipse((cx-30,cy+70,cx+30,cy+130), fill="#F28C28")
    elif "पतंग" in o:
        draw.polygon([(cx,cy-130),(cx+120,cy),(cx,cy+130),(cx-120,cy)], fill="#FF6B8A", outline="#B93658")
        draw.line((cx,cy+130,cx+80,cy+280), fill="#666", width=6)
        draw.line((cx+30,cy+185,cx-25,cy+220), fill="#6BCB77", width=10)
    elif "गेंद" in o:
        draw.ellipse((cx-100,cy-100,cx+100,cy+100), fill="#FFD84D", outline="#D59E24", width=8)
        draw.arc((cx-80,cy-80,cx+80,cy+80), 30, 210, fill="#FF7A59", width=10)
    elif "नक्शा" in o:
        rounded(draw,(cx-130,cy-100,cx+130,cy+100),20,"#F4E4B2", "#A98B55", 7)
        draw.line((cx-85,cy+50,cx-20,cy-30,cx+35,cy+20,cx+90,cy-55), fill="#6FA8FF", width=10)
    elif "किताब" in o:
        rounded(draw,(cx-135,cy-105,cx+5,cy+115),12,"#E85C75","#A53B52",6)
        rounded(draw,(cx-5,cy-105,cx+135,cy+115),12,"#6FA8FF","#3E6EA8",6)
        draw.line((cx,cy-95,cx,cy+100), fill="white", width=5)
    elif "सितारा" in o:
        pts=[]
        for i in range(10):
            a=-90+i*36
            r=125 if i%2==0 else 55
            import math
            pts.append((cx+r*math.cos(math.radians(a)),cy+r*math.sin(math.radians(a))))
        draw.polygon(pts, fill="#FFD84D", outline="#D39E22")
    elif "फूल" in o:
        for dx,dy in [(0,-55),(55,0),(0,55),(-55,0)]:
            draw.ellipse((cx+dx-55,cy+dy-55,cx+dx+55,cy+dy+55), fill="#FF8FB1")
        draw.ellipse((cx-45,cy-45,cx+45,cy+45), fill="#FFD84D")
        draw.line((cx,cy+45,cx,cy+180), fill="#4EAD62", width=16)
    elif "पेंसिल" in o:
        rounded(draw,(cx-30,cy-150,cx+30,cy+150),18,"#FFD84D","#B68B22",6)
        draw.polygon([(cx-30,cy-150),(cx+30,cy-150),(cx,cy-220)], fill="#E8C49A")
    else:
        rounded(draw,(cx-110,cy-90,cx+110,cy+90),25,"#9AD9FF","#4D91B8",7)


def scene_image(story, scene, index, path):
    seed = int(hashlib.sha256((story.get("title","") + str(index)).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    img = Image.new("RGB", (WIDTH, HEIGHT), "#BFE8FF")
    d = ImageDraw.Draw(img)

    # cheerful sky/ground
    sky = ["#BFE8FF","#CFF5D2","#FFE7B3","#DCCBFF","#BDE9FF","#FFF1B8","#CDE7FF"][index % 7]
    d.rectangle((0,0,WIDTH,HEIGHT), fill=sky)
    d.ellipse((WIDTH-330,100,WIDTH-80,350), fill="#FFD84D")
    for x in [100, 360, 700]:
        d.ellipse((x,220,x+180,300), fill="white")
        d.ellipse((x+55,170,x+250,300), fill="white")
    # hills
    d.ellipse((-250,1050,700,1750), fill="#8FD69B")
    d.ellipse((400,1050,1300,1750), fill="#78C88A")
    d.rectangle((0,1350,WIDTH,HEIGHT), fill="#79C987")
    # decorative flowers/stars
    for _ in range(14):
        x=rng.randint(40,WIDTH-40); y=rng.randint(1200,1800)
        d.ellipse((x-12,y-12,x+12,y+12), fill=rng.choice(["#FF8FB1","#FFD84D","#FFFFFF"]))

    # Determine the main animal and object from story text.
    character = story.get("character", story.get("title", "खरगोश"))
    joined = " ".join([character, scene.get("visual", ""), story.get("topic", "")])
    object_name = next((o for o in OBJECTS if o.split()[0] in joined or o in joined), OBJECTS[index % len(OBJECTS)])
    if "पतंग" in joined: object_name = "उड़ने वाली पतंग"
    if "चाबी" in joined: object_name = "चमकती चाबी"
    if "गेंद" in joined: object_name = "सुनहरी गेंद"
    if "फूल" in joined: object_name = "रंग बदलने वाला फूल"

    # Main character position varies by scene so the stills do not feel identical.
    cx = [330,430,620,470,650,420,540][index]
    cy = [930,980,1000,930,980,940,930][index]
    draw_character(d, character, cx, cy, happy=index != 1)
    draw_object(d, object_name, 800 if index % 2 == 0 else 250, 780 if index % 2 == 0 else 700)

    # Small visual cue: a soft action trail / sparkles.
    for k in range(7):
        x = 120 + ((k * 137 + index * 91) % 800)
        y = 480 + ((k * 83 + index * 57) % 470)
        r = 7 + (k % 3) * 4
        d.ellipse((x-r,y-r,x+r,y+r), fill="#FFFFFF")

    # Keep a tiny episode badge without depending on Hindi text rendering.
    rounded(d, (55,55,265,130), 25, "#FFFFFF")
    d.text((90,72), f"SCENE {index+1}", font=font(34, True), fill="#4C6FFF")
    img.save(path, quality=95)


def ffmpeg_run(args):
    print("🔧", " ".join(str(x) for x in args))
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        print(result.stdout[-6000:])
        raise RuntimeError("FFmpeg command failed")
    return result.stdout


def animate_scene(image_path, tts_path, out_path, index):
    # zoompan provides continuous motion from a single locally-rendered cartoon frame.
    # Different scenes use different pan directions for variety.
    if index % 4 == 0:
        z = "min(zoom+0.0009,1.10)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif index % 4 == 1:
        z = "min(zoom+0.0007,1.08)"
        x = "(iw-iw/zoom)*on/(d-1)"
        y = "ih/2-(ih/zoom/2)"
    elif index % 4 == 2:
        z = "min(zoom+0.0008,1.09)"
        x = "(iw-iw/zoom)*(1-on/(d-1))"
        y = "ih/2-(ih/zoom/2)"
    else:
        z = "1.06"
        x = "iw/2-(iw/zoom/2)"
        y = "(ih-ih/zoom)*(on/(d-1))"

    vf = (
        f"scale=1280:2276:force_original_aspect_ratio=increase," 
        f"crop=1280:2276," 
        f"zoompan=z='{z}':x='{x}':y='{y}':d={SCENE_SECONDS*FPS}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        "format=yuv420p"
    )
    ffmpeg_run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-i", str(tts_path),
        "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
        "-t", str(SCENE_SECONDS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-r", str(FPS), "-pix_fmt", "yuv420p",
        "-af", "apad=pad_dur=8,atrim=0:8,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", str(out_path),
    ])


def concat_scenes(scene_paths):
    concat_file = WORK / "concat.txt"
    concat_file.write_text("".join(f"file '{p.resolve()}'\n" for p in scene_paths), encoding="utf-8")
    ffmpeg_run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart", str(OUT),
    ])


async def make_tts(text, output_path):
    communicate = edge_tts.Communicate(text=text, voice="hi-IN-SwaraNeural", rate=TTS_RATE)
    await communicate.save(str(output_path))


def make_tts_sync(text, output_path):
    asyncio.run(make_tts(text, output_path))


def upload_youtube(story):
    if not UPLOAD_YOUTUBE:
        print("ℹ️ YouTube upload disabled")
        return None

    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError("Missing YouTube OAuth secrets")

    credentials = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    youtube = build("youtube", "v3", credentials=credentials)

    title = str(story.get("title", "Toon Kids Story"))[:95]
    if RUN_SLOT == "0":
        title = f"{title} 🐰 | Kids Story #Shorts"
    elif RUN_SLOT == "1":
        title = f"{title} 🌈 | Kids Story #Shorts"
    else:
        title = f"{title} 🎈 | Kids Story #Shorts"

    description = (
        f"{story.get('topic','')}\n\n"
        f"🌟 Moral: {story.get('moral','')}\n\n"
        "प्यारी हिंदी बच्चों की कहानी, fun cartoon adventure और learning के साथ। "
        "ऐसी मजेदार kids stories के लिए subscribe करें!\n\n"
        "#Shorts #Kids #KidsStory #HindiStory #Cartoon #KidsVideo #MoralStory"
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "24",
            "tags": ["kids", "kids story", "hindi story", "cartoon", "moral story", "children story", "youtube shorts"],
            "defaultLanguage": "hi",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": True},
    }

    print("📤 Uploading to YouTube...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(OUT), mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"📤 Upload: {int(status.progress() * 100)}%")
    video_id = response.get("id")
    print(f"✅ YouTube uploaded: https://youtu.be/{video_id}")
    return video_id


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    print("==========================================")
    print("TOON KIDS — FREE LOCAL ANIMATION")
    print("==========================================")
    print(f"Text model: {TEXT_MODEL}")
    print(f"Scenes: {SCENE_COUNT} x {SCENE_SECONDS}s")
    print("Video generator: NONE (Pillow + FFmpeg)")
    print(f"Run slot: {RUN_SLOT}")

    for p in WORK.glob("*"):
        if p.is_file():
            p.unlink()

    history = load_history()
    story = None

    # Gemini is optional. If its free quota is exhausted, the workflow continues locally.
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            for attempt in range(5):
                topic = choose_topic(history)
                candidate = make_story(client, topic, history)
                candidate["topic"] = topic
                if not is_duplicate(candidate, history):
                    story = candidate
                    break
                print(f"⚠️ Duplicate-like story detected; regenerating ({attempt + 1}/5)")
        except Exception as exc:
            print(f"⚠️ Gemini unavailable/exhausted; switching to local story: {exc}")

    if story is None:
        story = local_story(history)
        print("🆓 Local fallback story selected — no text API required.")

    print(f"📖 Story: {story.get('title')}")
    print(f"💡 Moral: {story.get('moral')}")

    scene_paths = []
    for i, scene in enumerate(story["scenes"]):
        image_path = WORK / f"scene_art_{i+1:02d}.png"
        narration_audio = WORK / f"tts_{i+1:02d}.mp3"
        final_scene = WORK / f"scene_{i+1:02d}.mp4"

        print(f"🎨 Drawing cartoon scene {i+1}/{SCENE_COUNT}")
        scene_image(story, scene, i, image_path)
        print(f"🗣️ Generating Hindi narration {i+1}/{SCENE_COUNT}")
        make_tts_sync(scene["narration"], narration_audio)
        print(f"🎞️ Animating scene {i+1}/{SCENE_COUNT}")
        animate_scene(image_path, narration_audio, final_scene, i)
        scene_paths.append(final_scene)

    concat_scenes(scene_paths)

    metadata = {
        "title": story.get("title", ""),
        "topic": story.get("topic", ""),
        "moral": story.get("moral", ""),
        "scene_count": SCENE_COUNT,
        "scene_seconds": SCENE_SECONDS,
        "target_duration_seconds": SCENE_COUNT * SCENE_SECONDS,
        "video_generator": "local_pillow_ffmpeg",
        "text_model": TEXT_MODEL if api_key else "local_fallback",
        "run_slot": RUN_SLOT,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    video_id = upload_youtube(story)
    if video_id:
        metadata["youtube_video_id"] = video_id
        metadata["youtube_url"] = f"https://youtu.be/{video_id}"

    META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    fingerprint = hashlib.sha256(norm(story_text(story)).encode("utf-8")).hexdigest()
    history.append({
        "title": story.get("title", ""),
        "topic": story.get("topic", ""),
        "moral": story.get("moral", ""),
        "story_text": story_text(story),
        "fingerprint": fingerprint,
        "youtube_video_id": video_id,
        "created_at_utc": metadata["created_at_utc"],
    })
    save_history(history)

    print("==========================================")
    print("✅ TOON KIDS SHORT COMPLETE")
    print(f"🎥 Output: {OUT}")
    print(f"⏱️ Duration target: {SCENE_COUNT * SCENE_SECONDS}s")
    if video_id:
        print(f"📺 YouTube: https://youtu.be/{video_id}")
    print("==========================================")


if __name__ == "__main__":
    main()
