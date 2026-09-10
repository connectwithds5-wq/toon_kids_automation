import asyncio
import json
import math
import os
import random
import shutil
import subprocess
import wave
from pathlib import Path

from google import genai
from google.genai import types
import edge_tts
from gradio_client import Client, handle_file
from PIL import Image, ImageDraw

from toon_kids_story import WORK, load_history, is_duplicate, story_text, draw_character, draw_object

SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TEXT_MODEL = (os.getenv("GEMINI_TEXT_MODEL") or "gemini-2.5-flash-lite").strip()
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_gemini_wan_production.mp4"))
SCENES = 4
SCENE_SECONDS = 4.5
FPS = 16
W, H = 1080, 1920
VOICE = os.getenv("TOON_VOICE", "hi-IN-SwaraNeural")


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        print(p.stdout[-8000:])
        raise RuntimeError("FFmpeg command failed")
    return p.stdout


def duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True)
    return float(out.strip())


def extract_video(result):
    if isinstance(result, dict):
        for k in ("video", "output", "file", "path"):
            if isinstance(result.get(k), str) and result[k]: return result[k]
    if isinstance(result, (list, tuple)):
        for x in result:
            try:
                p = extract_video(x)
                if p: return p
            except RuntimeError: pass
    if isinstance(result, str) and result: return result
    raise RuntimeError(f"No video path in HF result: {result!r}")


def generate_story():
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY is required for the Gemini production workflow")
    history = load_history()
    old = [x.get("title", "") for x in history[-30:] if isinstance(x, dict)]
    prompt = f"""
You are the senior writer for a premium Hindi preschool animated Shorts channel.
Create ONE original 18-second micro-story for children age 3-7.
Use EXACTLY 4 scenes, each 4.5 seconds.
The story must be simple -> funny/curious -> small emotional payoff -> happy lesson.
No scary content, violence, danger, weapons, sadness, death or conflict.
Use one main animal character and at most one small friend.
Keep the same character design in every scene.

Return ONLY valid JSON with:
{{
 "title":"catchy Hindi title",
 "character":"fixed visual character description: species, body colors, outfit, accessory, eye color",
 "setting":"rich recurring environment",
 "moral":"short positive lesson",
 "scenes":[
  {{"narration":"7-9 natural spoken Hindi words", "visual":"specific visible action and scenery", "camera":"slow cinematic camera move", "emotion":"emotion", "sfx":"one sound cue"}}
 ]
}}

Timing rules: every narration must comfortably fit about 2.8-3.6 seconds at normal Hindi speech. Never use filler words or long clauses. Keep each line short enough to finish before the scene's SFX.
Visual rules: describe concrete scenery, foreground/background depth, lighting, props and character action. Each scene must visibly change while preserving the same character.
Audio rules: one clear SFX per scene, placed AFTER the narration as a punctuation beat, never underneath dialogue. Scene 1 hook, scene 2 discovery, scene 3 action, scene 4 payoff + moral.
Avoid these previous titles: {json.dumps(old, ensure_ascii=False)}
"""
    client = genai.Client(api_key=GEMINI_KEY)
    for attempt in range(4):
        r = client.models.generate_content(model=TEXT_MODEL, contents=prompt, config=types.GenerateContentConfig(temperature=0.85, response_mime_type="application/json"))
        story = json.loads(r.text)
        if len(story.get("scenes", [])) != SCENES: continue
        if not is_duplicate(story, history): return story
        prompt += "\nIMPORTANT: previous result was too similar; create a completely different story."
    raise RuntimeError("Gemini could not produce a unique 4-scene story")


def rich_scene(story, scene, index, path):
    seed = hash((story["title"], index)) & 0xffffffff
    rng = random.Random(seed)
    img = Image.new("RGB", (W, H), "#A9DFFF")
    d = ImageDraw.Draw(img)
    palettes = [
        ("#A9DFFF", "#78C98A", "#F8D36A"),
        ("#C9B8FF", "#79C58B", "#FFD86B"),
        ("#FFE2A8", "#6FC58A", "#FF9DB7"),
        ("#B8E7FF", "#72BE83", "#FFD35C"),
    ]
    sky, ground, sun = palettes[index % len(palettes)]
    d.rectangle((0, 0, W, H), fill=sky)
    d.ellipse((760, 120, 1010, 370), fill=sun)
    for x, y in [(80, 240), (420, 180), (680, 310)]:
        d.ellipse((x, y, x+180, y+80), fill="white")
        d.ellipse((x+45, y-45, x+220, y+75), fill="white")
    d.ellipse((-320, 980, 720, 1690), fill="#91D89A")
    d.ellipse((390, 1030, 1370, 1710), fill="#7BC989")
    d.rectangle((0, 1360, W, H), fill=ground)
    d.polygon([(430, H), (650, H), (585, 1450), (520, 1350), (475, 1450)], fill="#E8C58A")
    for x in [75, 900]:
        d.rectangle((x+55, 900, x+85, 1370), fill="#7B5A3A")
        d.ellipse((x-40, 760, x+180, 1010), fill="#58A96C")
        d.ellipse((x+30, 700, x+240, 980), fill="#69BA77")
    for _ in range(18):
        x = rng.randint(30, W-30); y = rng.randint(1300, 1810)
        r = rng.choice([7, 9, 12])
        d.ellipse((x-r, y-r, x+r, y+r), fill=rng.choice(["#FF8FB1", "#FFD84D", "#FFFFFF"]))
    for k in range(8):
        x = 120 + ((k * 149 + index * 71) % 780)
        y = 470 + ((k * 91 + index * 53) % 620)
        d.ellipse((x-5, y-5, x+5, y+5), fill="white")
    character = story.get("character", "प्यारा cartoon animal")
    joined = " ".join([character, story.get("setting", ""), scene.get("visual", ""), scene.get("sfx", "")])
    obj = next((o for o in ["चमकती चाबी", "जादुई घंटी", "उड़ने वाली पतंग", "सुनहरी गेंद", "रहस्यमयी नक्शा", "जादुई किताब", "चमकता सितारा", "रंग बदलने वाला फूल", "संगीत बॉक्स", "जादुई पेंसिल"] if o in joined), None)
    if obj:
        draw_object(d, obj, 780 if index % 2 == 0 else 290, 820)
    positions = [(390, 1040), (560, 1010), (420, 1060), (570, 1030)]
    cx, cy = positions[index]
    draw_character(d, character, cx, cy, happy=True)
    for x in [0, 1030]:
        d.ellipse((x-100, 1570, x+180, 1960), fill="#4F9C68")
    img.save(path, quality=95)


def make_clip(client, story, scene, index):
    image = WORK / f"prod_scene_{index+1}.png"
    clip = WORK / f"prod_scene_{index+1}.mp4"
    rich_scene(story, scene, index, image)
    prompt = (
        "Premium preschool 3D cartoon animation from the supplied first frame. "
        "The supplied image is the exact visual identity reference. Preserve the main character "
        "EXACTLY: same species, face, eyes, body proportions, colors, clothes and accessories. "
        f"Character identity: {story['character']}. Environment: {story.get('setting','')}. "
        f"Visible action: {scene['visual']}. Emotion: {scene.get('emotion','happy')}. "
        f"Camera: {scene.get('camera','slow gentle cinematic push in')}. "
        "Slow natural animation, subtle head/ear/body movement, gentle object motion, stable anatomy, "
        "stable face, stable clothes, cinematic depth, soft lighting, polished children's TV look. "
        "Do not run, jump rapidly, morph, redesign, duplicate characters or shake the camera. "
        "No text, letters, subtitles, logos, watermarks, badges or UI."
    )[:1100]
    negative = "text, letters, subtitles, logo, watermark, badge, UI, fast motion, rapid camera, shake, blur, low quality, face morph, character morph, identity change, clothing change, extra limbs, duplicate character, deformed hands, flicker, jitter, artifact"
    result = client.predict(handle_file(str(image)), prompt, 6, negative, SCENE_SECONDS, 1.0, 1.0, 8100+index, False, api_name="/generate_video")
    source = Path(extract_video(result))
    if not source.is_file(): raise FileNotFoundError(source)
    shutil.copy2(source, clip)
    return clip


async def make_tts(text, path):
    await edge_tts.Communicate(text=text, voice=VOICE, rate="+0%").save(str(path))


def fit_voice(src, dst, target):
    d = duration(src)
    if d > target - 0.18:
        factor = min(1.16, d / (target - 0.18))
    else:
        factor = 1.0
    pitch = 1.045
    tempo = factor / pitch
    run(["ffmpeg", "-y", "-i", str(src), "-af", f"asetrate=44100*{pitch:.4f},aresample=44100,atempo={tempo:.5f},atrim=0:{target-0.08:.3f},apad=pad_dur=0.08", "-t", str(target), "-ar", "44100", "-ac", "1", str(dst)])


def make_music(path, seconds):
    rate=44100; total=int(seconds*rate); chords=[(261.63,329.63,392),(220,277.18,329.63),(246.94,311.13,369.99),(196,246.94,293.66)]
    melody=[523.25,587.33,659.25,783.99,659.25,587.33,523.25,493.88]
    vals=[]
    for i in range(total):
        t=i/rate; c=chords[int(t/2.25)%4]; pad=sum(math.sin(2*math.pi*f*t) for f in c)/3
        n=melody[int((t%2)/.25)%len(melody)]; env=max(0,1-((t%0.25)/0.25))**2
        bell=math.sin(2*math.pi*n*t)*0.045*env
        vals.append(0.075*pad+bell)
    with wave.open(str(path),'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        wf.writeframes(b''.join(int(max(-1,min(1,x))*32767).to_bytes(2,'little',signed=True) for x in vals))


def sfx(path, kind):
    rate=44100; dur=0.28 if kind in ("pop","tap") else 0.42; count=int(dur*rate); vals=[]
    base={"sparkle":1320,"chime":880,"whoosh":180,"pop":260,"tap":520}.get(kind,440)
    for i in range(count):
        t=i/rate; f=base + (700*t if kind=="whoosh" else 180*t); env=min(1,t/.015,(dur-t)/.08)
        vals.append(math.sin(2*math.pi*f*t)*(0.10 if kind=="whoosh" else 0.13)*max(0,env))
    with wave.open(str(path),'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        wf.writeframes(b''.join(int(max(-1,min(1,x))*32767).to_bytes(2,'little',signed=True) for x in vals))


def kind(name):
    n=name.lower()
    if any(x in n for x in ["चमक","रोशनी","सरप्राइज"]): return "sparkle"
    if any(x in n for x in ["खुल","घंटी","चाबी"]): return "chime"
    if any(x in n for x in ["उड़","दौड़","हवा","पतंग"]): return "whoosh"
    if any(x in n for x in ["दरवाजा","टप","कदम"]): return "tap"
    return "pop"


def ass_file(story, scenes, voices, path):
    lines=["[Script Info]","ScriptType: v4.00+","PlayResX:1080","PlayResY:1920","","[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding","Style: Kids,Noto Sans Devanagari,56,&H00FFFFFF,&H00FFFFFF,&H001B263B,&H90000000,1,5,2,2,60,60,145,1","","[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    def ts(x):
        m=int(x//60); s=x-m*60; return f"{m}:{s:04.1f}"
    for i,(sc,v) in enumerate(zip(scenes,voices)):
        a=i*SCENE_SECONDS; b=min(a+duration(v), (i+1)*SCENE_SECONDS-0.05)
        text=str(sc['narration']).replace('{','(').replace('}',')')
        lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Kids,,0,0,0,,{text}")
    path.write_text('\n'.join(lines),encoding='utf-8')


def main():
    if not GEMINI_KEY: raise RuntimeError("GEMINI_API_KEY missing")
    WORK.mkdir(exist_ok=True)
    for p in WORK.glob("prod_*.*"):
        p.unlink()
    story=generate_story(); print("GEMINI STORY:", json.dumps(story,ensure_ascii=False,indent=2))
    scenes=story["scenes"][:SCENES]
    client=Client(SPACE, token=HF_TOKEN)
    clips=[]
    for i,sc in enumerate(scenes): clips.append(make_clip(client,story,sc,i))
    concat=WORK/"prod_video.mp4"; cf=WORK/"prod_concat.txt"
    cf.write_text(''.join(f"file '{p.resolve()}'\\n" for p in clips),encoding='utf-8')
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cf),"-an","-t",str(SCENES*SCENE_SECONDS),"-c:v","libx264","-preset","veryfast","-crf","18","-r",str(FPS),"-pix_fmt","yuv420p",str(concat)])
    voices=[]; sfxs=[]
    for i,sc in enumerate(scenes):
        raw=WORK/f"prod_voice_raw_{i}.mp3"; v=WORK/f"prod_voice_{i}.wav"; s=WORK/f"prod_sfx_{i}.wav"
        asyncio.run(make_tts(sc['narration'],raw)); fit_voice(raw,v,SCENE_SECONDS); sfx(s,kind(sc.get('sfx',''))); voices.append(v); sfxs.append(s)
    music=WORK/"prod_music.wav"; make_music(music,SCENES*SCENE_SECONDS)
    ass=WORK/"prod_subs.ass"; ass_file(story,scenes,voices,ass)
    cmd=["ffmpeg","-y","-i",str(concat),"-i",str(music)]
    for v,s in zip(voices,sfxs): cmd += ["-i",str(v),"-i",str(s)]
    filters=["[1:a]volume=0.08[m0]"]; voice_labels=[]; sfx_labels=[]
    sfx_delays=[]
    for i in range(SCENES):
        vi=2+i*2; si=vi+1; scene_start=i*SCENE_SECONDS
        voice_delay=int(round(scene_start*1000))
        filters += [f"[{vi}:a]adelay={voice_delay}|{voice_delay},volume=1.0[v{i}]"]
        voice_labels.append(f"[v{i}]")
        voice_len=duration(voices[i])
        sfx_time=min(scene_start + voice_len + 0.08, (i+1)*SCENE_SECONDS - 0.48)
        sfx_delay=int(round(max(scene_start, sfx_time)*1000))
        sfx_delays.append(sfx_delay)
        filters += [f"[{si}:a]adelay={sfx_delay}|{sfx_delay},volume=0.38[s{i}]"]
        sfx_labels.append(f"[s{i}]")
    filters += ["".join(voice_labels)+f"amix=inputs={SCENES}:duration=longest:normalize=0[duckkey]", "[m0][duckkey]sidechaincompress=threshold=0.025:ratio=8:attack=8:release=280:makeup=1[ducked]"]
    mix="[ducked]"+"".join(voice_labels)+"".join(sfx_labels)+f"amix=inputs={1+SCENES+SCENES}:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=8[aout]"
    filters.append(mix)
    sub=ass.as_posix().replace('\\','/').replace("'","\\'")
    cmd += ["-filter_complex",";".join(filters),"-map","0:v:0","-map","[aout]","-vf",f"subtitles='{sub}'","-t",str(SCENES*SCENE_SECONDS),"-c:v","libx264","-preset","veryfast","-crf","19","-r",str(FPS),"-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-ar","44100","-movflags","+faststart",str(OUT)]
    run(cmd)
    print("FINAL",OUT,"duration",duration(OUT))
    print("TITLE",story["title"])
    print("MORAL",story["moral"])

if __name__ == "__main__": main()
