import asyncio
import math
import os
import shutil
import subprocess
import wave
from pathlib import Path

import edge_tts
from gradio_client import Client, handle_file
from PIL import Image, ImageFilter
from toon_kids_story import WORK, local_story, load_history, scene_image

SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None
OUT = Path(os.getenv("HF_WAN_OUTPUT", "toon_wan_10sec_story_av_v2.mp4"))
FINAL_SECONDS = 10.0
CLIP_SECONDS = 3.5
FPS = 24
W, H = 1080, 1920
SLOTS = [3.25, 3.35, 3.40]
NEGATIVE = "blurry, low quality, distorted face, deformed body, extra limbs, bad anatomy, duplicate character, character morphing, face morphing, flicker, jitter, unstable clothing, unstable colors, text, letters, subtitles, logo, watermark, rectangle artifact, gray frame, noisy image"


def run(cmd):
    print("🔧", " ".join(str(x) for x in cmd))
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode:
        print(r.stdout[-7000:])
        raise RuntimeError("Command failed")
    return r.stdout


def get_video(result):
    if isinstance(result, dict):
        for k in ("video", "output", "file", "path"):
            v = result.get(k)
            if isinstance(v, str) and v: return v
    if isinstance(result, (tuple, list)):
        for x in result:
            if isinstance(x, str) and (x.endswith((".mp4", ".webm", ".mov", ".mkv")) or Path(x).is_file()): return x
            try: return get_video(x)
            except RuntimeError: pass
    if isinstance(result, str) and result: return result
    raise RuntimeError(f"No video path: {result!r}")


def clean_anchor(story, scene, index):
    raw = WORK / f"v2_anchor_raw_{index}.png"
    out = WORK / f"v2_anchor_{index}.png"
    scene_image(story, scene, index, raw)
    img = Image.open(raw).convert("RGB")
    patch = img.crop((35, 35, 290, 155)).filter(ImageFilter.GaussianBlur(10))
    img.paste(patch.resize((255, 120)), (35, 35))
    img.save(out, quality=96)
    return out


def make_clip(client, story, scene, index, anchor):
    out = WORK / f"v2_clip_{index}.mp4"
    prompt = (
        "Premium polished 3D children's cartoon image-to-video animation. "
        "DO NOT redesign the input image. Preserve the EXACT same character identity, face, eyes, ears, trunk, body proportions, hat, scarf, bow, shirt, colors, object shapes and background style. "
        "Only animate the requested action. Never change species, clothes or colors. "
        f"Character: {story.get('character','cute cartoon animal')}. "
        f"Action: {scene.get('visual','')}. Camera: {scene.get('camera','gentle cinematic movement')}. "
        "Natural readable motion, stable anatomy, stable face, smooth child-friendly movement, gentle cinematic camera, bright polished animated-film look, vertical 9:16 composition, no text or watermark."
    )[:1100]
    print(f"🎬 Wan 2.2 scene {index+1}/3")
    result = client.predict(handle_file(str(anchor)), prompt, 6, NEGATIVE, CLIP_SECONDS, 1.0, 1.0, 9100+index, False, api_name="/generate_video")
    src = Path(get_video(result))
    if not src.is_file(): raise FileNotFoundError(src)
    shutil.copy2(src, out)
    return out


def write_wav(path, samples, rate=44100):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        raw = bytearray()
        for x in samples: raw += int(max(-1,min(1,x))*32767).to_bytes(2,"little",signed=True)
        wf.writeframes(raw)


def add_note(buf, start, length, freq, amp, rate=44100):
    a=max(0,int(start*rate)); b=min(len(buf),int((start+length)*rate))
    for i in range(a,b):
        t=i/rate-start
        env=min(1,t/.025)*max(0,(length-t)/.14)
        v=math.sin(2*math.pi*freq*t)+.35*math.sin(2*math.pi*2*freq*t)+.15*math.sin(2*math.pi*3*freq*t)
        buf[i]+=amp*v*max(0,env)


def make_music(path):
    rate=44100; buf=[0.0]*int(FINAL_SECONDS*rate)
    chords=[(261.63,329.63,392.0),(220.0,277.18,329.63),(246.94,311.13,369.99),(196.0,246.94,293.66)]
    melody=[523.25,587.33,659.25,587.33,523.25,493.88,440.0,493.88]
    for bar,ch in enumerate(chords):
        t=bar*2.5
        for f in ch: add_note(buf,t,2.2,f,.020,rate)
        for j in range(5): add_note(buf,t+j*.5,.32,melody[(bar*2+j)%len(melody)],.040,rate)
    write_wav(path,buf,rate)


def make_sfx(path, kind):
    rate=44100; buf=[0.0]*int(.8*rate)
    if kind=="sparkle":
        for off,f in ((0,880),(.10,1175),(.20,1568),(.31,1760)): add_note(buf,off,.38,f,.085,rate)
    elif kind=="chime":
        for off,f in ((0,659),(.12,988),(.24,1319)): add_note(buf,off,.55,f,.09,rate)
    elif kind=="whoosh":
        for i in range(len(buf)):
            t=i/rate; env=min(1,t/.05)*max(0,1-t/.75)
            buf[i]+=.055*math.sin(2*math.pi*(100+1200*t)*t)*env
    else: add_note(buf,0,.22,392,.08,rate)
    write_wav(path,buf,rate)


def sfx_kind(scene):
    text=scene.get('visual','')+' '+scene.get('narration','')
    if any(x in text for x in ('चमक','रोशनी','खुशी','सरप्राइज')): return 'sparkle'
    if any(x in text for x in ('खुल','दरवाजा','चाबी')): return 'chime'
    if any(x in text for x in ('दौड़','ऊपर','उड़','पतंग')): return 'whoosh'
    return 'pop'


async def tts(text,path):
    await edge_tts.Communicate(text=text,voice='hi-IN-SwaraNeural',rate='+10%').save(str(path))


def tts_sync(text,path): asyncio.run(tts(text,path))


def dur(path):
    return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nk=1',str(path)]).strip().splitlines()[-1])


def fit_voice(src,dst,target):
    d=max(.2,dur(src)); ratio=min(2.0,max(.5,d/max(.45,target-.10)))
    run(['ffmpeg','-y','-i',str(src),'-af',f'atempo={ratio:.5f},apad,atrim=0:{target:.3f},loudnorm=I=-18:TP=-2:LRA=8','-ar','44100','-ac','1','-c:a','aac','-b:a','128k',str(dst)])


def make_ass(scenes,path):
    def ts(x):
        m=int(x//60); s=x-m*60
        return f"0:{m:02d}:{s:05.2f}"
    lines=['[Script Info]','ScriptType: v4.00+','PlayResX: 1080','PlayResY: 1920','', '[V4+ Styles]',
      'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
      'Style: Kids,Noto Sans Devanagari,54,&H00FFFFFF,&H00FFFFFF,&H0015222D,&H99000000,1,0,0,0,100,100,0,0,1,4,1,2,55,55,175,1','', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    start=0
    for scene,slot in zip(scenes,SLOTS):
        end=min(FINAL_SECONDS,start+slot)
        text=str(scene.get('narration','')).replace('{','(').replace('}',')')
        lines.append(f'Dialogue: 0,{ts(start)},{ts(end)},Kids,,0,0,0,,{text}')
        start=end
    path.write_text('\n'.join(lines),encoding='utf-8')


def assemble(clips,out):
    parts=[]
    for i,(clip,slot) in enumerate(zip(clips,SLOTS)):
        part=WORK/f'v2_part_{i}.mp4'
        run(['ffmpeg','-y','-i',str(clip),'-t',f'{slot:.3f}','-vf',f'scale={W}:{H}:flags=lanczos,setsar=1','-an','-c:v','libx264','-preset','veryfast','-crf','19','-r',str(FPS),'-pix_fmt','yuv420p',str(part)])
        parts.append(part)
    f=WORK/'v2_concat.txt'; f.write_text('\n'.join(f"file '{x.resolve()}'" for x in parts),encoding='utf-8')
    run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(f),'-t',str(FINAL_SECONDS),'-an','-c:v','libx264','-preset','veryfast','-crf','19','-r',str(FPS),'-pix_fmt','yuv420p',str(out)])


def mux(video,music,voices,sfxs,sub,out):
    cmd=['ffmpeg','-y','-i',str(video),'-i',str(music)]
    for v,s in zip(voices,sfxs): cmd += ['-i',str(v),'-i',str(s)]
    filters=['[1:a]volume=0.10[m]']; mix=['[m]']; cursor=0
    for i,slot in enumerate(SLOTS):
        vi=2+i*2; si=vi+1; vd=int(cursor*1000); sd=int((cursor+.42)*1000)
        filters += [f'[{vi}:a]adelay={vd}|{vd},volume=1.10[v{i}]',f'[{si}:a]adelay={sd}|{sd},volume=0.48[s{i}]']
        mix += [f'[v{i}]',f'[s{i}]']; cursor+=slot
    filters.append(''.join(mix)+f'amix=inputs={len(mix)}:duration=longest:dropout_transition=0,loudnorm=I=-15.5:TP=-1.5:LRA=10[aout]')
    vf=f"subtitles='{sub.as_posix()}':fontsdir=/usr/share/fonts/truetype,setsar=1"
    cmd += ['-filter_complex',';'.join(filters),'-map','0:v','-map','[aout]','-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','19','-r',str(FPS),'-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-shortest',str(out)]
    run(cmd)
