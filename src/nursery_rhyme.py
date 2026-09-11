import secrets
from toon_kids_story import load_history, is_duplicate


# Original, short, public-domain-safe style nursery-rhyme concepts.
# Each visual is deliberately written for cinematic 3D image/video generation.
RHYME_STORIES = [
    {
        "title": "छोटा खरगोश धूम मचाए",
        "topic": "एक प्यारा खरगोश रंगीन फूलों की घाटी में उछलता, दौड़ता और दोस्तों के साथ तितलियों के पीछे भागता है।",
        "moral": "खेलो, गाओ और दोस्तों के साथ खुश रहो।",
        "character": "एक छोटा fluffy सफेद खरगोश, लंबे गुलाबी कान, नीली छोटी hoodie, चमकती बड़ी भूरी आँखें, गोल गाल",
        "rhyme": "कूदे खरगोश टप-टप-टप, फूलों में वह झटपट झप।\nदौड़े, गाए, हँसे ज़रा, दोस्तों संग दिन है खरा!",
        "scenes": [
            {"narration": "कूदे खरगोश टप-टप-टप, फूलों में वह झटपट झप!", "visual": "खरगोश रंगीन फूलों वाली विशाल घाटी में खुशी से उछलता है, कान हवा में लहराते हैं।", "camera": "low-angle tracking shot, gentle push forward"},
            {"narration": "दौड़े, गाए, हँसे ज़रा, दोस्तों संग दिन है खरा!", "visual": "खरगोश दो प्यारे छोटे दोस्तों के साथ हरी घास पर दौड़ता है, तितलियाँ चारों ओर उड़ती हैं।", "camera": "dynamic side tracking shot with soft motion blur"},
            {"narration": "सूरज हँसे, रंग बरसे, खुशियों से ये पल सँवरें!", "visual": "तीनों दोस्त पहाड़ी के ऊपर रुककर चमकते सूर्यास्त और उड़ती रंगीन तितलियों को देखते हैं, फिर खुशी से हाथ हिलाते हैं।", "camera": "cinematic crane up, wide reveal"},
        ],
    },
    {
        "title": "नन्हा हाथी झूमे झूम",
        "topic": "एक नन्हा हाथी जंगल के संगीत में सूंड हिलाते हुए नाचता है और दोस्तों के साथ मजेदार ताल बनाता है।",
        "moral": "साथ मिलकर गाना और नाचना खुशी बढ़ाता है।",
        "character": "एक नन्हा नीला हाथी, बड़ी प्यारी आँखें, पीली छोटी टोपी, लाल scarf, मुलायम realistic skin",
        "rhyme": "हाथी झूमे झूम-झूम-झूम, बजती जंगल की प्यारी धुन।\nटप-टप पाँव और सूंड हिले, सारे दोस्त मिलकर दिल खिलें!",
        "scenes": [
            {"narration": "हाथी झूमे झूम-झूम-झूम, बजती जंगल की प्यारी धुन!", "visual": "नन्हा हाथी सुबह के जादुई जंगल में ताल पर खुशी से झूमता है, पेड़ों से सुनहरी किरणें आती हैं।", "camera": "dolly-in with gentle orbit"},
            {"narration": "टप-टप पाँव और सूंड हिले, सारे दोस्त मिलकर दिल खिलें!", "visual": "हाथी खरगोश और बंदर दोस्तों के साथ पत्तों से बने छोटे musical instruments बजाते हुए नाचता है।", "camera": "energetic circular tracking shot"},
            {"narration": "हँसी की ताल पर जंगल गाए, खुशी के रंग सभी पर छाए!", "visual": "सभी दोस्त चमकते जंगल clearing में साथ नाचते हैं, fireflies और फूल हवा में सुंदर depth के साथ चमकते हैं।", "camera": "cinematic crane-out wide shot"},
        ],
    },
    {
        "title": "चूजा बोले चीं-चीं",
        "topic": "एक नन्हा पीला चूजा सुबह के खेत में चीं-चीं करते हुए रंगीन फूलों और दोस्तों के साथ खेलता है।",
        "moral": "हर नई सुबह खुशी और खेल लेकर आती है।",
        "character": "एक छोटा fluffy पीला चूजा, नारंगी चोंच और पैर, बड़ी चमकदार काली आँखें, छोटा हरा scarf",
        "rhyme": "चूजा बोले चीं-चीं-चीं, सुबह हुई तो चमकी ज़मीं।\nफूल खिले और पंछी गाएँ, आओ मिलकर खेल रचाएँ!",
        "scenes": [
            {"narration": "चूजा बोले चीं-चीं-चीं, सुबह हुई तो चमकी ज़मीं!", "visual": "नन्हा चूजा ओस से चमकते खेत में सूर्योदय के समय दौड़ता है, सुनहरी रोशनी और फूलों की depth दिखती है।", "camera": "ground-level tracking shot"},
            {"narration": "फूल खिले और पंछी गाएँ, आओ मिलकर खेल रचाएँ!", "visual": "चूजा रंगीन फूलों के बीच छोटे पक्षी दोस्तों के साथ गोल-गोल घूमकर खेलता है।", "camera": "smooth orbit with shallow depth of field"},
            {"narration": "चीं-चीं की मीठी तान, सुबह बने खुशियों की जान!", "visual": "चूजा और दोस्त छोटी पहाड़ी पर खड़े होकर उजली सुबह देखते हैं और खुशी से पंख हिलाते हैं।", "camera": "slow cinematic pull-back"},
        ],
    },
]


def local_rhyme(history=None):
    history = history if history is not None else load_history()
    candidates = [item for item in RHYME_STORIES if not is_duplicate(item, history)]
    if candidates:
        return secrets.choice(candidates)
    return secrets.choice(RHYME_STORIES)
