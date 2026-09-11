"""Racing-specific story pack for the cinematic Wan 2.2 pipeline."""

import json
import secrets
from pathlib import Path

from toon_kids_story import WORK, HISTORY, load_history, is_duplicate

RACING_STORIES = [
    {
        "title": "लाल बिजली बनाम नीला तूफान",
        "topic": "दो futuristic race cars sunset mountain circuit पर रोमांचक race में आमने-सामने आते हैं।",
        "moral": "अच्छी race में जीत से ज्यादा जरूरी fair play और हिम्मत है।",
        "character": "sleek scarlet-red futuristic race car, low aerodynamic body, glossy metallic paint, black racing wheels, bright white LED headlights, distinctive lightning-shaped side stripe",
        "scenes": [
            {"narration":"सूरज ढलते ही लाल रेस कार तेज़ी से शुरुआती लाइन पर पहुँचती है।", "visual":"A glossy scarlet-red futuristic race car launches from a starting grid on a mountain circuit at sunset, tires gripping asphalt, dramatic dust and tiny sparks, grandstands and glowing track lights in the distance.", "camera":"very low front three-quarter tracking shot, 24mm anamorphic lens, aggressive speed perspective"},
            {"narration":"सुरंग में लाल कार नीली कार के साथ पहिए से पहिया मिलाकर दौड़ती है।", "visual":"The red race car battles a sleek cobalt-blue rival through a neon-lit mountain tunnel, side by side at extreme speed, reflections streaking across polished bodywork, wheels spinning rapidly.", "camera":"low side wheel-level chase shot, fast parallax, controlled motion blur, cinematic tunnel light streaks"},
            {"narration":"आखिरी मोड़ पर दोनों कारें साथ निकलती हैं और दोस्ती से फिनिश करती हैं।", "visual":"The two futuristic race cars explode out of the final mountain corner into golden sunset, racing toward a bright finish line together, then slowing side by side as sparks and dust settle behind them.", "camera":"high drone dive into a sweeping low tracking finish-line shot, dramatic lens flare, epic final reveal"},
        ],
    },
    {
        "title": "टर्बो रेस का आखिरी मोड़",
        "topic": "एक छोटी futuristic race car कठिन coastal circuit पर आखिरी मोड़ में शानदार comeback करती है।",
        "moral": "हार मत मानो, आखिरी पल तक कोशिश करते रहो।",
        "character": "compact electric-orange futuristic race car, muscular aerodynamic silhouette, glossy orange metallic paint, matte-black roof, glowing cyan headlights, wide performance tires",
        "scenes": [
            {"narration":"नारंगी टर्बो कार समुद्र किनारे रेस ट्रैक पर पूरी ताकत से दौड़ती है।", "visual":"A compact electric-orange futuristic race car rockets along a dramatic coastal racing circuit, ocean cliffs on one side and barriers on the other, sunset reflections on wet asphalt.", "camera":"low rear chase camera, 28mm anamorphic lens, fast road-level tracking"},
            {"narration":"आगे वाली कार मोड़ पर निकल जाती है, लेकिन टर्बो कार हार नहीं मानती।", "visual":"The orange car closes the gap through a sharp hairpin corner, suspension compressing, tires gripping hard, realistic tire smoke and subtle sparks, rival car just ahead.", "camera":"helicopter-style overhead sweep dropping into a tight inside-corner tracking shot"},
            {"narration":"आखिरी सेकंड में टर्बो कार बराबरी करती है और दोनों खुशी से फिनिश करते हैं।", "visual":"The orange car pulls alongside the rival on the final straight, both crossing the illuminated finish line together against a spectacular ocean sunset, cinematic celebration.", "camera":"front-facing low tracking shot transitioning to a wide aerial finish reveal"},
        ],
    },
]


def racing_story(history=None):
    history = history if history is not None else load_history()
    candidates = [story for story in RACING_STORIES if not is_duplicate(story, history)]
    return secrets.choice(candidates or RACING_STORIES)
