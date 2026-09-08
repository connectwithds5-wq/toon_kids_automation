import asyncio
import hashlib
import json
import random
import time
from pathlib import Path

from PIL import Image, ImageDraw

from toon_kids_story import (
    HISTORY,
    WORK,
    animate_scene,
    concat_scenes,
    draw_object,
    font,
    load_history,
    norm,
    scene_image,
)

# ============================================================
# TOON KIDS — KIDS STUDY STORY MODE
# 100% local story selection: no Gemini, no Kaggle GPU, no video API.
# Fun story + learning concept + Hindi narration + cartoon motion.
# 7 scenes x 8 sec = ~56 sec Short.
# ============================================================

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_study_short.mp4"
META = BASE / "study_story_metadata.json"
STUDY_HISTORY = BASE / "study_story_history.json"
SCENE_COUNT = 7
SCENE_SECONDS = 8
TTS_RATE = "+5%"

# Each episode teaches one small concept through a playful problem.
EPISODES = [
    {
        "title": "गोलू की गाजरों का जादू",
        "learning": "छोटी गणित: 5 में से 2 घटे तो 3 बचते हैं",
        "concept": "subtraction",
        "character": "छोटा सफेद खरगोश, गुलाबी कान, नीली छोटी जैकेट, गोल प्यारी आँखें",
        "topic": "एक शरारती खरगोश अपनी गाजरों की गिनती करते हुए मजेदार तरीके से घटाना सीखता है।",
        "moral": "गिनकर सोचें तो मुश्किल सवाल भी खेल जैसा आसान हो जाता है।",
        "scenes": [
            {"narration":"गोलू खरगोश ने टोकरी में पाँच कुरकुरी गाजरें रखीं और खुशी से गिनने लगा।", "visual":"खरगोश पाँच गाजरों वाली टोकरी देखकर उछलता है।", "learning":"1 2 3 4 5!", "camera":"gentle push in"},
            {"narration":"तभी गोलू ने दो गाजरें अपने दोस्त पिंटू को खाने के लिए दे दीं।", "visual":"खरगोश दो गाजरें दोस्त को प्यार से देता है।", "learning":"5 − 2", "camera":"slow pan right"},
            {"narration":"गोलू ने माथा खुजाया, फिर टोकरी में बची गाजरों को गिनना शुरू किया।", "visual":"खरगोश टोकरी में बची गाजरों को ध्यान से गिनता है।", "learning":"अब कितनी?", "camera":"gentle tracking"},
            {"narration":"एक गाजर, दो गाजर, तीन गाजर! गोलू की आँखें खुशी से चमक उठीं।", "visual":"खरगोश तीन गाजरों की ओर इशारा करके खुशी मनाता है।", "learning":"3 बचीं!", "camera":"slow reveal"},
            {"narration":"पिंटू बोला, पाँच में से दो गए, इसलिए तीन गाजरें बचीं!", "visual":"दोनों दोस्त उँगलियों से पाँच, दो और तीन का मजेदार इशारा करते हैं।", "learning":"5 − 2 = 3", "camera":"push in"},
            {"narration":"गोलू ने हँसकर कहा, अरे! गणित तो गाजर खाने जितना मजेदार है!", "visual":"खरगोश मजेदार अंदाज में गाजर खाता है और दोस्त हँसते हैं।", "learning":"Math is fun!", "camera":"gentle zoom out"},
            {"narration":"दोनों दोस्तों ने मिलकर फिर गिना और बोले, पाँच में से दो घटे तो तीन बचते हैं!", "visual":"दोनों दोस्त तीन गाजरों के साथ खुशी से हाथ हिलाते हैं।", "learning":"5 − 2 = 3 ✓", "camera":"gentle push in"},
        ],
    },
    {
        "title": "मीमी का रंगों वाला सरप्राइज",
        "learning": "रंग पहचान: लाल, पीला और नीला",
        "concept": "colors",
        "character": "प्यारी बिल्ली, सफेद फर, गुलाबी कान, बैंगनी छोटी ड्रेस, गोल चमकदार आँखें",
        "topic": "एक प्यारी बिल्ली रंगीन फूलों की खोज में लाल, पीला और नीला पहचानना सीखती है।",
        "moral": "ध्यान से देखकर सीखना सबसे मजेदार खेल है।",
        "scenes": [
            {"narration":"मीमी बिल्ली को बगीचे में तीन चमकीले फूलों वाला एक रहस्यमयी रास्ता मिला।", "visual":"बिल्ली रंगीन फूलों के रास्ते को देखकर उत्साहित होती है।", "learning":"आज रंग पहचानेंगे!", "camera":"gentle push in"},
            {"narration":"पहला फूल लाल था, बिल्कुल मीमी के छोटे से खिलौने जैसा चमकदार।", "visual":"बिल्ली लाल फूल को सूँघकर खुशी से मुस्कुराती है।", "learning":"लाल ❤️", "camera":"slow pan left"},
            {"narration":"दूसरा फूल पीला था, जैसे आसमान में चमकता प्यारा सूरज।", "visual":"बिल्ली पीले फूल के पास सूरज की ओर देखती है।", "learning":"पीला ☀️", "camera":"gentle tracking"},
            {"narration":"तीसरा फूल नीला था, जैसे साफ आसमान और चमकता छोटा तालाब।", "visual":"बिल्ली नीले फूल और छोटे तालाब को देखकर खुश होती है।", "learning":"नीला 💙", "camera":"slow reveal"},
            {"narration":"अचानक हवा चली और तीनों फूल गोल गोल घूमने लगे, मीमी खिलखिला दी।", "visual":"रंगीन फूल हवा में झूमते हैं और बिल्ली मजेदार ढंग से घूमती है।", "learning":"लाल • पीला • नीला", "camera":"push in"},
            {"narration":"मीमी ने बिना भूले तीनों रंग दोबारा बताए और अपने दोस्त को भी सिखाए।", "visual":"बिल्ली तीन फूलों की ओर बारी बारी से इशारा करती है।", "learning":"3 colors!", "camera":"gentle zoom out"},
            {"narration":"अब रंगों का खेल शुरू हुआ और मीमी बोली, सीखना कितना मजेदार है!", "visual":"बिल्ली रंगीन फूलों के बीच खुशी से नाचती है।", "learning":"लाल + पीला + नीला ✓", "camera":"gentle push in"},
        ],
    },
    {
        "title": "टिंकू और तीन आकारों का खजाना",
        "learning": "आकार पहचान: गोला, त्रिकोण और वर्ग",
        "concept": "shapes",
        "character": "नन्हा पांडा, काले कान, लाल छोटी टोपी, नीली जैकेट, बड़ी प्यारी आँखें",
        "topic": "एक नन्हा पांडा रहस्यमयी खिलौनों में गोला, त्रिकोण और वर्ग पहचानकर खजाने तक पहुँचता है।",
        "moral": "ध्यान से पहचानना हमें सही रास्ता दिखाता है।",
        "scenes": [
            {"narration":"टिंकू पांडा को जंगल में एक ताला मिला जिस पर तीन आकारों के निशान बने थे।", "visual":"पांडा रहस्यमयी दरवाजे पर तीन आकार देखकर सोचता है।", "learning":"Shapes hunt!", "camera":"gentle push in"},
            {"narration":"पहला निशान गोल था, बिल्कुल टिंकू की उछलती गेंद जैसा गोल गोल।", "visual":"पांडा गोल गेंद उठाकर निशान से मिलाता है।", "learning":"गोला ○", "camera":"slow pan right"},
            {"narration":"दूसरा निशान त्रिकोण था, जिसकी तीन नुकीली भुजाएँ थीं।", "visual":"पांडा तीन कोनों वाले त्रिकोण को ध्यान से देखता है।", "learning":"त्रिकोण △", "camera":"gentle tracking"},
            {"narration":"तीसरा निशान वर्ग था, जिसकी चार बराबर सीधी भुजाएँ थीं।", "visual":"पांडा चौकोर खिलौना उठाकर चार किनारे गिनता है।", "learning":"वर्ग □", "camera":"slow reveal"},
            {"narration":"टिंकू ने तीनों आकार सही क्रम में लगाए और दरवाजा टनटनाकर खुल गया।", "visual":"पांडा तीन आकार सही जगह लगाता है और दरवाजा चमकता है।", "learning":"○ △ □", "camera":"push in"},
            {"narration":"अंदर कोई डरावना खजाना नहीं, बल्कि रंगीन खिलौनों की मजेदार टोकरी थी।", "visual":"पांडा खिलौनों की टोकरी देखकर खुशी से उछलता है।", "learning":"Shapes everywhere!", "camera":"gentle zoom out"},
            {"narration":"टिंकू बोला, गोला, त्रिकोण और वर्ग पहचानो, फिर खेलते खेलते सीखो!", "visual":"पांडा तीनों आकारों के खिलौनों के साथ खुशी से हाथ हिलाता है।", "learning":"○ △ □ ✓", "camera":"gentle push in"},
        ],
    },
]


def load_study_history():
    try:
        data = json.loads(STUDY_HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_study_history(data):
    STUDY_HISTORY.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def story_fingerprint(story):
    text = " ".join([story.get("title", ""), story.get("learning", ""), story.get("topic", "")] + [s.get("narration", "") for s in story.get("scenes", [])])
    return hashlib.sha256(norm(text).encode("utf-8")).hexdigest()


def choose_episode(history):
    used = {item.get("fingerprint") for item in history if isinstance(item, dict)}
    candidates = [e for e in EPISODES if story_fingerprint(e) not in used]
    if not candidates:
        # Rotate predictably after the curated set is consumed.
        candidates = EPISODES
    return random.SystemRandom().choice(candidates)


def overlay_learning_card(image_path, learning, scene_index):
    img = Image.open(image_path).convert("RGB")
    d = ImageDraw.Draw(img)
    # High-contrast but compact learning cue, kept below the scene badge.
    box = (55, 150, 1025, 285)
    d.rounded_rectangle(box, radius=28, fill="white", outline="#5B6CFF", width=5)
    label = f"सीखें • {learning}"
    f = font(42, True)
    d.text((85, 185), label, font=f, fill="#3447B8")
    img.save(image_path, quality=95)


def main():
    print("==========================================")
    print("TOON KIDS — KIDS STUDY STORY MODE")
    print("==========================================")
    print("Story generation: LOCAL CURATED — no Gemini")
    print("Video generation: Pillow + FFmpeg — no GPU")
    print(f"Scenes: {SCENE_COUNT} x {SCENE_SECONDS}s = ~{SCENE_COUNT * SCENE_SECONDS}s")

    for p in WORK.glob("*"):
        if p.is_file():
            p.unlink()

    history = load_study_history()
    story = json.loads(json.dumps(choose_episode(history), ensure_ascii=False))
    print(f"📚 Learning: {story['learning']}")
    print(f"📖 Story: {story['title']}")

    scene_paths = []
    for i, scene in enumerate(story["scenes"]):
        image_path = WORK / f"study_scene_art_{i+1:02d}.png"
        narration_audio = WORK / f"study_tts_{i+1:02d}.mp3"
        final_scene = WORK / f"study_scene_{i+1:02d}.mp4"

        print(f"🎨 Drawing study scene {i+1}/{SCENE_COUNT}")
        scene_image(story, scene, i, image_path)
        overlay_learning_card(image_path, scene["learning"], i)
        print(f"🗣️ Hindi narration {i+1}/{SCENE_COUNT}")
        asyncio.run(__import__("toon_kids_story").make_tts(scene["narration"], narration_audio))
        print(f"🎞️ Animating scene {i+1}/{SCENE_COUNT}")
        animate_scene(image_path, narration_audio, final_scene, i)
        scene_paths.append(final_scene)

    concat_scenes(scene_paths)
    # Base concat writes toon_kids_short.mp4; keep the study output separate.
    base_out = BASE / "toon_kids_short.mp4"
    if base_out.exists():
        base_out.replace(OUT)

    metadata = {
        "title": story["title"],
        "topic": story["topic"],
        "learning": story["learning"],
        "concept": story["concept"],
        "moral": story["moral"],
        "scene_count": SCENE_COUNT,
        "scene_seconds": SCENE_SECONDS,
        "target_duration_seconds": SCENE_COUNT * SCENE_SECONDS,
        "story_mode": "kids_study_local",
        "story_generation": "curated_local_no_gemini",
        "video_generator": "local_pillow_ffmpeg_no_gpu",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    history.append({"title": story["title"], "learning": story["learning"], "concept": story["concept"], "fingerprint": story_fingerprint(story)})
    save_study_history(history[-50:])
    print(f"✅ Created: {OUT}")
    print(f"📦 Size: {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
