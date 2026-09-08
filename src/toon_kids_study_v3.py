import asyncio
import hashlib
import json
import math
import random
import subprocess
import time
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from toon_kids_story import make_tts

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "toon_kids_study_short.mp4"
META = BASE / "study_story_metadata.json"
HISTORY = BASE / "study_story_history.json"
WORK = BASE / "work_study_v3"
WORK.mkdir(exist_ok=True)

W, H = 540, 960
FPS = 12
SCENE_SECONDS = 8
SCENES = 7
DURATION = SCENE_SECONDS * SCENES
TTS_RATE = "+0%"

STORY = {
    "title": "चीकू का उल्टी गिनती रॉकेट",
    "learning": "उल्टी गिनती: 10 से 1",
    "concept": "countdown",
    "topic": "चीकू खरगोश अपना छोटा रॉकेट उड़ाते हुए 10 से 1 तक उल्टी गिनती सीखता है।",
    "moral": "खेल-खेल में गिनती सीखना सबसे मजेदार है!",
    "character": "चीकू, छोटा सफेद खरगोश, गुलाबी कान, नीली जैकेट, गोल चमकदार आँखें",
    "narration": [
        "चीकू खरगोश आज अपना छोटा रॉकेट उड़ाने वाला था, लेकिन उसे उल्टी गिनती सीखनी थी।",
        "रॉकेट तैयार हुआ! चीकू बोला, दस से शुरू करेंगे, फिर हर बार एक संख्या कम करेंगे।",
        "दस, नौ, आठ! चीकू हँसते हुए बटन दबाता गया और रॉकेट की लाइटें चमकने लगीं।",
        "सात, छह, पाँच! अब चीकू को समझ आया कि हर कदम पर एक संख्या कम हो रही है।",
        "चार, तीन, दो, एक! चीकू ने हेलमेट पहना और जोर से बोला, अब उड़ान होगी!",
        "शूँऽऽ! रॉकेट आसमान में पहुँचा और चीकू ने तारों के साथ फिर से गिनती दोहराई।",
        "दस से एक तक उल्टी गिनती पूरी! चीकू बोला, देखा, खेलते खेलते गिनती कितनी आसान है!",
    ],
    "learning_cards": ["10", "10 9 8", "7 6 5", "4 3 2", "1", "10 9 8 7 6 5 4 3 2 1", "10 → 9 → 8 → 7 → 6 → 5 → 4 → 3 → 2 → 1"],
}


def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf" if bold else "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def centered(draw, text, y, f, fill="white", stroke=0, stroke_fill="black"):
    box = draw.textbbox((0, 0), text, font=f, stroke_width=stroke)
    x = (W - (box[2] - box[0])) / 2
    draw.text((x, y), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)


def rounded(draw, box, r, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def rabbit(draw, x, y, s=1.0, bounce=0):
    y += bounce
    # ears
    draw.ellipse((x-38*s, y-115*s, x-5*s, y-15*s), fill="#F28EAA", outline="#9B5268", width=max(1,int(3*s)))
    draw.ellipse((x+5*s, y-115*s, x+38*s, y-15*s), fill="#F28EAA", outline="#9B5268", width=max(1,int(3*s)))
    # head
    draw.ellipse((x-58*s,y-65*s,x+58*s,y+50*s), fill="#FFFFFF", outline="#7A7A7A", width=max(1,int(3*s)))
    # eyes
    for ex in (x-22*s,x+22*s):
        draw.ellipse((ex-7*s,y-30*s,ex+7*s,y-8*s), fill="#202638")
        draw.ellipse((ex-4*s,y-27*s,ex+1*s,y-22*s), fill="white")
    draw.arc((x-25*s,y-5*s,x+25*s,y+25*s), 10, 170, fill="#B64E69", width=max(1,int(3*s)))
    # blue jacket
    rounded(draw,(x-52*s,y+42*s,x+52*s,y+125*s),18*s,"#4F73D9","#2D468D",max(1,int(3*s)))
    draw.ellipse((x-32*s,y+57*s,x-20*s,y+69*s),outline="white",width=max(1,int(2*s)))
    draw.ellipse((x+20*s,y+57*s,x+32*s,y+69*s),outline="white",width=max(1,int(2*s)))
    # feet
    draw.ellipse((x-50*s,y+112*s,x-12*s,y+137*s),fill="#F0A8B8")
    draw.ellipse((x+12*s,y+112*s,x+50*s,y+137*s),fill="#F0A8B8")


def rocket(draw, x, y, s=1.0, flame=0):
    # body
    draw.ellipse((x-42*s,y-90*s,x+42*s,y+95*s), fill="#F4F5FA", outline="#4B5870", width=max(1,int(4*s)))
    draw.polygon([(x-42*s,y+50*s),(x-80*s,y+85*s),(x-42*s,y+85*s)], fill="#FF647C")
    draw.polygon([(x+42*s,y+50*s),(x+80*s,y+85*s),(x+42*s,y+85*s)], fill="#FF647C")
    draw.ellipse((x-22*s,y-42*s,x+22*s,y+2*s), fill="#55A8E8", outline="#365D86", width=max(1,int(3*s)))
    draw.rectangle((x-13*s,y+68*s,x+13*s,y+92*s), fill="#FFD447")
    # flame flicker
    fl = 45 + 25*abs(math.sin(flame*10))
    draw.polygon([(x-18*s,y+90*s),(x+18*s,y+90*s),(x,y+90*s+fl*s)], fill="#FF9D32")
    draw.polygon([(x-9*s,y+90*s),(x+9*s,y+90*s),(x,y+90*s+fl*0.65*s)], fill="#FFE05C")


def background(draw, t, scene):
    skies=["#74C9FF","#A9E5C1","#C9B5FF","#FFD98A","#79C8FF","#6B9BEA","#FFB7CF"]
    draw.rectangle((0,0,W,H),fill=skies[scene%len(skies)])
    # moving clouds
    for k in range(4):
        x=((k*180 + t*18*(1 if k%2 else -1))%700)-80
        y=110+k*70
        draw.ellipse((x,y,x+100,y+45),fill="white")
        draw.ellipse((x+35,y-25,x+145,y+50),fill="white")
    # stars / sparkles
    rng=random.Random(500+scene)
    for i in range(22):
        x=rng.randint(20,W-20); y=rng.randint(260,650)
        pulse=2+int(2*abs(math.sin(t*4+i)))
        draw.ellipse((x-pulse,y-pulse,x+pulse,y+pulse),fill="#FFF5A6")
    # ground
    draw.ellipse((-180,650,380,1120),fill="#65BE7C")
    draw.ellipse((180,620,760,1120),fill="#55AD6B")
    draw.rectangle((0,780,W,H),fill="#55AD6B")


def top_bar(draw, scene):
    rounded(draw,(20,20,W-20,105),22,"white","#566DFF",3)
    centered(draw,"चीकू का मजेदार मिशन",38,font(30,True),fill="#263C9A")
    rounded(draw,(35,125,W-35,195),18,"#FFFFFF")
    centered(draw,"उल्टी गिनती सीखो!",143,font(28,True),fill="#E84F72")


def learning_card(draw, text):
    rounded(draw,(25,815,W-25,925),24,"#182647")
    f=font(32,True)
    # fit long English-ish numeral sequence
    if len(text)>25: f=font(21,True)
    centered(draw,text,850,f,fill="white")


def frame(scene, t):
    img=Image.new("RGB",(W,H))
    d=ImageDraw.Draw(img)
    background(d,t,scene)
    top_bar(d,scene)
    bounce=8*math.sin(t*5)

    if scene==0:
        rabbit(d,155,575,1.15,bounce)
        rocket(d,390,565,1.15, t)
        centered(d,"रॉकेट तैयार? 🚀",300,font(42,True),fill="#FFFFFF",stroke=3,stroke_fill="#31507A")
        # ten stars in two rows
        for i in range(10):
            x=90+(i%5)*90; y=390+(i//5)*55
            d.text((x,y),"★",font=font(38,True),fill="#FFD447")
        learning_card(d,"10")
    elif scene in (1,2,3,4):
        rabbit_x=130+scene*25+45*math.sin(t*2)
        rocket_x=390+20*math.sin(t*2.5)
        rabbit(d,rabbit_x,590,1.05,bounce)
        rocket(d,rocket_x,575,1.1,t)
        if scene==1: nums="10   9   8"
        elif scene==2: nums="7   6   5"
        elif scene==3: nums="4   3   2"
        else: nums="1"
        centered(d,nums,285,font(58,True),fill="#FFF",stroke=2,stroke_fill="#30446D")
        # bouncing countdown balls
        vals=nums.split()
        for i,v in enumerate(vals):
            bx=120+i*150; by=405+25*math.sin(t*4+i)
            d.ellipse((bx-48,by-48,bx+48,by+48),fill="#FFEA72",outline="#E59D2D",width=4)
            centered_local=d
            f=font(42,True); bb=d.textbbox((0,0),v,font=f); tw=bb[2]-bb[0]; th=bb[3]-bb[1]
            d.text((bx-tw/2,by-th/2-5),v,font=f,fill="#573D00")
        learning_card(d,nums)
    elif scene==5:
        # flying sequence
        rx=115+65*t; ry=570-30*math.sin(t*2)-35*t
        rocket(d,rx,ry,1.0,t)
        rabbit(d,115,ry+5,0.95,8*math.sin(t*6))
        centered(d,"आसमान में गिनती!",285,font(39,True),fill="white",stroke=3,stroke_fill="#31507A")
        # moving numbered stars
        seq=[10,9,8,7,6,5,4,3,2,1]
        for i,v in enumerate(seq):
            x=(40+i*62+t*22)%570; y=370+((i*71)%280)
            d.ellipse((x-22,y-22,x+22,y+22),fill="#FFE66D")
            f=font(18,True); bb=d.textbbox((0,0),str(v),font=f)
            d.text((x-(bb[2]-bb[0])/2,y-13),str(v),font=f,fill="#4B3C00")
        learning_card(d,"10 9 8 7 6 5 4 3 2 1")
    else:
        # landing celebration
        rabbit(d,150,575,1.2,12*math.sin(t*7))
        rocket(d,390,570,1.15,t)
        centered(d,"हमने कर ली! 🎉",275,font(45,True),fill="#FFF",stroke=3,stroke_fill="#9B3D62")
        centered(d,"10 → 9 → 8 → 7 → 6 → 5",350,font(24,True),fill="#FFF")
        centered(d,"→ 4 → 3 → 2 → 1",395,font(28,True),fill="#FFF")
        for i in range(14):
            x=(30+i*41)%W; y=450+35*math.sin(t*3+i)
            d.text((x,y),"✦",font=font(25,True),fill="#FFE45E")
        learning_card(d,"उल्टी गिनती = 10 से 1 ✓")
    return img


def make_music(path):
    # Simple royalty-free synthesized melody; no external audio asset or API.
    sr=22050
    notes=[523.25,659.25,783.99,659.25,587.33,698.46,880.0,698.46]
    samples=[]
    total=int(DURATION*sr)
    for i in range(total):
        t=i/sr
        note=notes[int(t*2)%len(notes)]
        amp=0.035*(1-min(1,(i%int(sr/2))/(sr*0.08))) if (i%int(sr/2))<int(sr*0.08) else 0.035
        v=amp*math.sin(2*math.pi*note*t)+0.012*math.sin(2*math.pi*note*2*t)
        samples.append(max(-1,min(1,v)))
    with wave.open(str(path),"wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        import struct
        wf.writeframes(b''.join(struct.pack('<h',int(v*32767)) for v in samples))


def run_ffmpeg(args):
    r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    if r.returncode:
        print(r.stdout[-7000:])
        raise RuntimeError("FFmpeg failed")


def render_scene(scene, tts_path, out_path):
    # Stream raw RGB frames directly to ffmpeg; no thousands of PNG files.
    cmd=["ffmpeg","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-i",str(tts_path),"-t",str(SCENE_SECONDS),"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p","-af","apad=pad_dur=8,atrim=0:8","-c:a","aac","-b:a","128k","-movflags","+faststart",str(out_path)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        for i in range(FPS*SCENE_SECONDS):
            img=frame(scene,i/FPS)
            proc.stdin.write(img.tobytes())
        proc.stdin.close()
        out=proc.stdout.read()
        rc=proc.wait()
        if rc: print(out.decode(errors="ignore")[-7000:]); raise RuntimeError("scene encode failed")
    finally:
        if proc.poll() is None: proc.kill()


def main():
    print("=== TOON KIDS STUDY V3 — DYNAMIC CARTOON ===")
    print("No Gemini • No Kaggle • No video API")
    for p in WORK.glob("*"):
        if p.is_file(): p.unlink()
    history=[]
    if HISTORY.exists():
        try: history=json.loads(HISTORY.read_text(encoding="utf-8"))
        except Exception: history=[]
    # Keep study history separate while allowing future rotation.
    audio_paths=[]; scene_paths=[]
    for i,text in enumerate(STORY["narration"]):
        tts=WORK/f"tts_{i+1:02d}.mp3"; scene_out=WORK/f"scene_{i+1:02d}.mp4"
        print(f"Scene {i+1}/{SCENES}: TTS + dynamic animation")
        asyncio.run(make_tts(text,tts))
        render_scene(i,tts,scene_out)
        audio_paths.append(tts); scene_paths.append(scene_out)

    concat=WORK/"concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in scene_paths),encoding="utf-8")
    music=WORK/"music.wav"; make_music(music)
    base=WORK/"base.mp4"
    run_ffmpeg(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(base)])
    run_ffmpeg(["ffmpeg","-y","-i",str(base),"-i",str(music),"-filter_complex","[1:a]volume=0.22[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]","-map","0:v:0","-map","[a]","-c:v","copy","-c:a","aac","-b:a","128k","-movflags","+faststart",str(OUT)])

    metadata={
        "title":STORY["title"],"topic":STORY["topic"],"learning":STORY["learning"],"concept":STORY["concept"],"moral":STORY["moral"],
        "scene_count":SCENES,"scene_seconds":SCENE_SECONDS,"target_duration_seconds":DURATION,
        "story_mode":"kids_study_dynamic_v3","story_generation":"local_curated_no_gemini","video_generator":"pillow_frame_animation_ffmpeg_no_gpu",
        "fps":FPS,"resolution":"1080x1920_final_from_540x960_render","created_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    }
    META.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    fp=hashlib.sha256(json.dumps(STORY,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    history.append({"title":STORY["title"],"learning":STORY["learning"],"concept":STORY["concept"],"fingerprint":fp})
    HISTORY.write_text(json.dumps(history[-50:],ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"DONE: {OUT} ({OUT.stat().st_size} bytes)")

if __name__=="__main__":
    main()
