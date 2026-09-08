import asyncio
import hashlib
import json
import math
import random
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import edge_tts

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_study_short.mp4"
META = BASE / "study_story_metadata.json"
HISTORY = BASE / "study_story_history.json"
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)
WIDTH, HEIGHT, FPS, SCENE_SECONDS = 1080, 1920, 30, 8
TTS_RATE = "+2%"

EPISODES = [
{"title":"चीकू का उल्टी गिनती रॉकेट 🚀","learning":"उल्टी गिनती: 10 से 1","concept":"countdown","character":"नन्हा सफेद खरगोश चीकू, गुलाबी कान, नीली स्पेस जैकेट, पीला बैग, बड़ी चमकदार आँखें","moral":"गिनती खेल बन जाए तो सीखना बहुत मजेदार हो जाता है।","scenes":[
("चीकू ने जंगल में अपना छोटा रॉकेट बनाया और बोला, आज चाँद तक उड़ेंगे!","रॉकेट तैयार","pad"),
("उड़ान से पहले चीकू ने दस चमकीले सितारे गिने और सबको रॉकेट में सजाया।","10 सितारे","stars"),
("अब उल्टी गिनती शुरू हुई: दस, नौ, आठ! चीकू ने बटन दबाया।","10 → 9 → 8","c10"),
("फिर आवाज आई: सात, छह, पाँच! रॉकेट मजेदार ढंग से हिलने लगा।","7 → 6 → 5","c7"),
("चीकू हँसा और बोला: चार, तीन, दो! बस अब एक बाकी है!","4 → 3 → 2","c4"),
("एक! फुस्स्स! रॉकेट आसमान में उड़ गया और चीकू खुशी से झूम उठा।","1 🚀","launch"),
("चीकू चाँद के पास पहुँचा और बोला, दस से एक उल्टी गिनती सीख ली!","10 9 8 7 6 5 4 3 2 1","moon")]},
{"title":"मीमी और रंग बदलने वाला बादल ☁️","learning":"रंग पहचान: लाल, पीला, नीला, हरा","concept":"colors","character":"प्यारी सफेद बिल्ली मीमी, गुलाबी कान, बैंगनी ड्रेस, पीला हेयरबो, बड़ी चमकदार आँखें","moral":"ध्यान से देखकर सीखना एक मजेदार खोज बन सकता है।","scenes":[
("मीमी को आसमान में एक छोटा बादल मिला जो हर बार रंग बदल रहा था!","रंगों का बादल","cloud"),
("बादल लाल हुआ, तो मीमी ने लाल फूल दिखाकर कहा, लाल!","लाल ❤️","red"),
("बादल पीला हुआ, तो मीमी ने सूरज की ओर देखकर कहा, पीला!","पीला ☀️","yellow"),
("बादल नीला हुआ, तो मीमी ने तालाब दिखाया और बोली, नीला!","नीला 💙","blue"),
("बादल हरा हुआ, तो मीमी ने पेड़ दिखाकर कहा, हरा!","हरा 💚","green"),
("बादल ने चारों रंग एक साथ चमकाए और मीमी गोल गोल नाचने लगी।","लाल • पीला • नीला • हरा","rainbow"),
("मीमी बोली, रंग पहचानना कितना आसान है! अब तुम भी रंग खोजो!","4 रंग ✓","final")]},
{"title":"टिंकू का आकारों वाला गुप्त दरवाजा 🔺","learning":"आकार पहचान: गोला, त्रिकोण, वर्ग","concept":"shapes","character":"नन्हा पांडा टिंकू, लाल टोपी, नीली जैकेट, काले कान, बड़ी चमकदार आँखें","moral":"ध्यान से पहचानो और सही आकार चुनो।","scenes":[
("टिंकू को जंगल में एक गुप्त दरवाजा मिला जिस पर तीन आकार चमक रहे थे।","गुप्त दरवाजा","door"),
("पहला निशान गोला था, बिल्कुल टिंकू की उछलती गेंद जैसा गोल!","गोला ○","circle"),
("दूसरा निशान त्रिकोण था, टिंकू ने उसके तीन कोने गिने: एक, दो, तीन!","त्रिकोण △ • 3 कोने","triangle"),
("तीसरा निशान वर्ग था, टिंकू ने उसके चार किनारे गिने: एक, दो, तीन, चार!","वर्ग □ • 4 किनारे","square"),
("टिंकू ने गोला, त्रिकोण और वर्ग सही जगह लगाए और दरवाजा खुल गया!","○ △ □","unlock"),
("अंदर रंगीन खिलौनों का खजाना था। टिंकू बोला, आकार हर जगह मिलते हैं!","Shapes everywhere!","treasure"),
("टिंकू ने तीनों आकार फिर दिखाए: गोला, त्रिकोण, वर्ग! वाह!","○ △ □ ✓","final")]}]

def font(size,bold=False):
    for p in (["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"] if bold else ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"]):
        if Path(p).exists(): return ImageFont.truetype(p,size)
    return ImageFont.load_default()

def text_center(d,text,y,f,fill="white",stroke=4):
    b=d.textbbox((0,0),text,font=f,stroke_width=stroke); d.text(((WIDTH-(b[2]-b[0]))//2,y),text,font=f,fill=fill,stroke_width=stroke,stroke_fill="#25314D")

def rounded(d,box,r,fill,outline=None,width=1): d.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=width)

def bg(seed,sky):
    rng=random.Random(seed); im=Image.new("RGB",(WIDTH,HEIGHT),sky); d=ImageDraw.Draw(im)
    d.ellipse((780,100,990,310),fill="#FFD84D")
    for x in [60,320,650]: d.ellipse((x,210,x+230,330),fill="white")
    d.ellipse((-300,1100,700,1780),fill="#7FD08E"); d.ellipse((400,1080,1320,1780),fill="#68BE7A"); d.rectangle((0,1400,WIDTH,HEIGHT),fill="#72C982")
    for _ in range(24):
        x=rng.randint(25,1055); y=rng.randint(1320,1830); d.ellipse((x-8,y-8,x+8,y+8),fill=rng.choice(["#FF8FB1","#FFD84D","#FFFFFF","#7ED6FF"]))
    return im,d

def rabbit(d,x,y,space=False):
    d.ellipse((x-125,y-145,x+125,y+105),fill="#F8F8F8",outline="#777",width=7)
    d.polygon([(x-90,y-70),(x-145,y-235),(x-25,y-120)],fill="#F08DA8"); d.polygon([(x+90,y-70),(x+145,y-235),(x+25,y-120)],fill="#F08DA8")
    for ex in (x-45,x+45): d.ellipse((ex-18,y-35,ex+18,y+25),fill="#202632"); d.ellipse((ex-8,y-27,ex+2,y-17),fill="white")
    d.arc((x-55,y+5,x+55,y+80),10,170,fill="#9A4055",width=8); rounded(d,(x-112,y+90,x+112,y+255),35,"#596DE8")
    if space: d.ellipse((x-92,y+115,x-35,y+172),outline="white",width=5); d.ellipse((x+35,y+115,x+92,y+172),outline="white",width=5)

def cat(d,x,y):
    d.ellipse((x-125,y-145,x+125,y+105),fill="white",outline="#777",width=7); d.polygon([(x-90,y-75),(x-150,y-220),(x-25,y-125)],fill="#F29BB5"); d.polygon([(x+90,y-75),(x+150,y-220),(x+25,y-125)],fill="#F29BB5")
    for ex in (x-45,x+45): d.ellipse((ex-18,y-35,ex+18,y+25),fill="#202632"); d.ellipse((ex-8,y-27,ex+2,y-17),fill="white")
    d.arc((x-55,y+5,x+55,y+80),10,170,fill="#A64058",width=8); rounded(d,(x-110,y+90,x+110,y+250),35,"#8E62D9")

def panda(d,x,y):
    d.ellipse((x-125,y-145,x+125,y+105),fill="white",outline="#343A46",width=7); d.ellipse((x-125,y-160,x-45,y-80),fill="#343A46"); d.ellipse((x+45,y-160,x+125,y-80),fill="#343A46")
    d.ellipse((x-95,y-35,x-25,y+45),fill="#343A46"); d.ellipse((x+25,y-35,x+95,y+45),fill="#343A46"); d.arc((x-52,y+8,x+52,y+78),10,170,fill="#A64058",width=8); rounded(d,(x-110,y+90,x+110,y+250),35,"#4E8EE7"); d.rectangle((x-105,y-195,x+105,y-125),fill="#E95D6E")

def rocket(d,x,y):
    d.ellipse((x-85,y-190,x+85,y+170),fill="#F2F4FA",outline="#4E5C7A",width=8); d.polygon([(x-85,y-120),(x-170,y+20),(x-80,y+10)],fill="#EF6B7F"); d.polygon([(x+85,y-120),(x+170,y+20),(x+80,y+10)],fill="#EF6B7F"); d.ellipse((x-48,y-100,x+48,y-4),fill="#69B9F2",outline="#365F8A",width=6); d.rectangle((x-22,y+105,x+22,y+170),fill="#FFD84D")

def draw_props(d,episode,kind):
    c=episode["concept"]
    if c=="countdown":
        rabbit(d,330,940,True); rocket(d,760,900)
        if kind=="pad":
            d.rectangle((550,1160,970,1220),fill="#56627A")
            for x in [600,760,920]: d.ellipse((x-20,1170,x+20,1210),fill="#FFD84D")
        elif kind=="stars":
            for i in range(10):
                x=520+(i%5)*110; y=390+(i//5)*100
                pts=[]
                for j in range(10): a=-math.pi/2+j*math.pi/5; r=34 if j%2==0 else 14; pts.append((x+r*math.cos(a),y+r*math.sin(a)))
                d.polygon(pts,fill="#FFD84D")
        nums={"c10":"10   9   8","c7":"7   6   5","c4":"4   3   2","launch":"1 🚀"}
        if kind in nums: text_center(d,nums[kind],430,font(96,True),stroke=5)
        if kind=="launch": d.polygon([(690,1120),(830,1120),(760,1510)],fill="#FF9E45")
        if kind=="moon":
            d.ellipse((650,420,1050,820),fill="#F2E6B7",outline="#B6A56D",width=8); rocket(d,760,1050); text_center(d,"WOW!",850,font(80,True),fill="#FFD84D")
    elif c=="colors":
        cat(d,350,940)
        cols={"red":"#F05B67","yellow":"#FFD84D","blue":"#4CA7E8","green":"#5BC27A"}
        if kind=="cloud":
            for x,y in [(650,560),(800,490),(940,570)]: d.ellipse((x-120,y-100,x+120,y+100),fill="white")
        elif kind=="rainbow":
            for i,col in enumerate(cols.values()): d.arc((550+i*18,430+i*18,1010-i*18,890-i*18),200,340,fill=col,width=38)
        else:
            col=cols.get(kind,"#8E62D9"); d.ellipse((680,520,980,820),fill=col,outline="white",width=10)
            d.ellipse((760,900,900,1040),fill=col)
    else:
        panda(d,350,940)
        if kind in ["door","unlock"]:
            rounded(d,(650,500,990,1160),40,"#A56BD6","#69429A",10); rounded(d,(720,570,920,1130),25,"#FFD84D","#B98B22",8)
            text_center(d,"○   △   □",650,font(62,True),stroke=2)
        elif kind=="circle": d.ellipse((680,570,950,840),fill="#FF7A8A",outline="white",width=10)
        elif kind=="triangle": d.polygon([(815,500),(650,850),(980,850)],fill="#FFD84D",outline="white")
        elif kind=="square": d.rectangle((660,540,960,840),fill="#62B8F0",outline="white",width=10)
        elif kind=="treasure":
            rounded(d,(630,680,1000,940),35,"#D79A42","#9A6A2D",8)
            for x,y,col in [(700,620,"#FF7A8A"),(810,570,"#FFD84D"),(920,620,"#62B8F0")]: d.ellipse((x-50,y-50,x+50,y+50),fill=col)
        elif kind=="final":
            for x,label,col in [(650,"○","#FF7A8A"),(810,"△","#FFD84D"),(970,"□","#62B8F0")]:
                if label=="○": d.ellipse((x-55,610,x+55,720),fill=col)
                elif label=="△": d.polygon([(x,590),(x-65,720),(x+65,720)],fill=col)
                else: d.rectangle((x-55,610,x+55,720),fill=col)

def make_image(ep,scene,i,path):
    im,d=bg(int(hashlib.sha256((ep["title"]+str(i)).encode()).hexdigest()[:8],16),["#A9DFFF","#C8F0D0","#FFE6A9","#D9C8FF"][i%4])
    draw_props(d,ep,scene[2])
    rounded(d,(40,40,1040,170),28,"white","#5268E8",5); d.text((75,78),f"EPISODE • SCENE {i+1}/7",font=font(34,True),fill="#5268E8")
    rounded(d,(40,205,1040,380),30,"white","#5268E8",5); text_center(d,scene[1],245,font(60,True),fill="#3447B8",stroke=2)
    rounded(d,(80,1620,1000,1805),38,"#25314D"); text_center(d,"देखो • सोचो • बोलो!",1665,font(56,True),stroke=2)
    im.save(path,quality=95)

def run(cmd):
    r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    if r.returncode: print(r.stdout[-5000:]); raise RuntimeError("FFmpeg failed")

def animate(image,audio,out,i):
    if i%4==0: z="min(zoom+0.0012,1.13)"; x="iw/2-(iw/zoom/2)"; y="ih/2-(ih/zoom/2)"
    elif i%4==1: z="min(zoom+0.0010,1.11)"; x="(iw-iw/zoom)*on/(duration-1)"; y="ih/2-(ih/zoom/2)"
    elif i%4==2: z="min(zoom+0.0010,1.11)"; x="(iw-iw/zoom)*(1-on/(duration-1))"; y="ih/2-(ih/zoom/2)"
    else: z="1.08"; x="iw/2-(iw/zoom/2)"; y="(ih-ih/zoom)*on/(duration-1)"
    vf=f"scale=1280:2276:force_original_aspect_ratio=increase,crop=1280:2276,zoompan=z='{z}':x='{x}':y='{y}':d={SCENE_SECONDS*FPS}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p"
    run(["ffmpeg","-y","-loop","1","-i",str(image),"-i",str(audio),"-map","0:v:0","-map","1:a:0","-vf",vf,"-t",str(SCENE_SECONDS),"-c:v","libx264","-preset","veryfast","-crf","22","-r",str(FPS),"-pix_fmt","yuv420p","-af","apad=pad_dur=8,atrim=0:8,loudnorm=I=-16:TP=-1.5:LRA=11","-c:a","aac","-b:a","128k","-ar","44100","-movflags","+faststart",str(out)])

async def tts(text,out): await edge_tts.Communicate(text=text,voice="hi-IN-SwaraNeural",rate=TTS_RATE).save(str(out))

def main():
    for p in WORK.glob("*"):
        if p.is_file(): p.unlink()
    try: history=json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception: history=[]
    used={x.get("title") for x in history if isinstance(x,dict)}; choices=[e for e in EPISODES if e["title"] not in used] or EPISODES; ep=random.SystemRandom().choice(choices)
    print("📚",ep["learning"]); print("📖",ep["title"])
    paths=[]
    for i,scene in enumerate(ep["scenes"]):
        img=WORK/f"fun_v2_art_{i+1:02d}.png"; aud=WORK/f"fun_v2_tts_{i+1:02d}.mp3"; clip=WORK/f"fun_v2_scene_{i+1:02d}.mp4"
        make_image(ep,scene,i,img); asyncio.run(tts(scene[0],aud)); animate(img,aud,clip,i); paths.append(clip)
    concat=WORK/"fun_v2_concat.txt"; concat.write_text("".join(f"file '{p.resolve()}'\n" for p in paths),encoding="utf-8")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy","-movflags","+faststart",str(OUT)])
    history.append({"title":ep["title"],"learning":ep["learning"],"concept":ep["concept"]}); HISTORY.write_text(json.dumps(history[-50:],ensure_ascii=False,indent=2),encoding="utf-8")
    META.write_text(json.dumps({"title":ep["title"],"learning":ep["learning"],"concept":ep["concept"],"moral":ep["moral"],"scene_count":7,"scene_seconds":8,"target_duration_seconds":56,"story_mode":"kids_study_fun_v2","video_generator":"local_pillow_ffmpeg","created_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())},ensure_ascii=False,indent=2),encoding="utf-8")
    print("✅",OUT,OUT.stat().st_size)

if __name__=="__main__": main()
