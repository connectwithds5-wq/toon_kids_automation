import asyncio, hashlib, json, math, random, subprocess, time, wave, struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import edge_tts

BASE=Path(__file__).resolve().parent.parent
OUT=BASE/'toon_kids_study_short.mp4'; META=BASE/'study_story_metadata.json'; HISTORY=BASE/'study_story_history.json'; WORK=BASE/'work_dynamic'; WORK.mkdir(exist_ok=True)
W,H,FPS,SEC=540,960,12,8

STORY={
 'title':'चीकू का उल्टी गिनती रॉकेट','learning':'उल्टी गिनती: 10 से 1','concept':'countdown','moral':'खेल-खेल में गिनती सीखना सबसे मजेदार है!',
 'narration':[
 'चीकू खरगोश आज अपना छोटा रॉकेट उड़ाने वाला था, लेकिन उसे उल्टी गिनती सीखनी थी।',
 'रॉकेट तैयार हुआ! चीकू बोला, दस से शुरू करेंगे और हर बार एक संख्या कम करेंगे।',
 'दस, नौ, आठ! चीकू बटन दबाता गया और रॉकेट की लाइटें चमकने लगीं।',
 'सात, छह, पाँच! चीकू समझ गया कि हर कदम पर एक संख्या कम हो रही है।',
 'चार, तीन, दो, एक! चीकू ने हेलमेट पहना और बोला, अब उड़ान होगी!',
 'शूँ! रॉकेट आसमान में पहुँचा और चीकू ने तारों के साथ गिनती दोहराई।',
 'दस से एक तक उल्टी गिनती पूरी! चीकू बोला, खेलते खेलते गिनती कितनी आसान है!'],
 'cards':['10','10  9  8','7  6  5','4  3  2','1','10 9 8 7 6 5 4 3 2 1','10 → 9 → 8 → 7 → 6 → 5 → 4 → 3 → 2 → 1']}


def F(n,b=False):
 for p in ['/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf' if b else '/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf','/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf' if b else '/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf']:
  if Path(p).exists(): return ImageFont.truetype(p,n)
 return ImageFont.load_default()

def text(d,s,y,size=34,fill='white',bold=True,stroke=0,sc='black'):
 f=F(size,bold); box=d.textbbox((0,0),s,font=f,stroke_width=stroke); x=(W-(box[2]-box[0]))/2; d.text((x,y),s,font=f,fill=fill,stroke_width=stroke,stroke_fill=sc)

def box(d,b,r,fill,outline=None,w=1): d.rounded_rectangle(b,radius=r,fill=fill,outline=outline,width=w)

def rabbit(d,x,y,s=1,b=0):
 y+=b
 d.ellipse((x-38*s,y-130*s,x-5*s,y-20*s),fill='#F28EAA',outline='#914F67',width=max(1,int(3*s));); d.ellipse((x+5*s,y-130*s,x+38*s,y-20*s),fill='#F28EAA',outline='#914F67',width=max(1,int(3*s)))
 d.ellipse((x-62*s,y-72*s,x+62*s,y+52*s),fill='white',outline='#687080',width=max(1,int(3*s)))
 for ex in (x-23*s,x+23*s): d.ellipse((ex-8*s,y-35*s,ex+8*s,y-10*s),fill='#202638'); d.ellipse((ex-4*s,y-32*s,ex+1*s,y-27*s),fill='white')
 d.arc((x-28*s,y-8*s,x+28*s,y+28*s),10,170,fill='#B84B68',width=max(1,int(3*s)))
 box(d,(x-55*s,y+45*s,x+55*s,y+140*s),20*s,'#4F73D9','#30498E',max(1,int(3*s)))
 d.ellipse((x-34*s,y+62*s,x-22*s,y+74*s),outline='white',width=max(1,int(2*s))); d.ellipse((x+22*s,y+62*s,x+34*s,y+74*s),outline='white',width=max(1,int(2*s)))
 d.ellipse((x-52*s,y+125*s,x-10*s,y+150*s),fill='#F0A8B8'); d.ellipse((x+10*s,y+125*s,x+52*s,y+150*s),fill='#F0A8B8')

def rocket(d,x,y,s=1,fl=0):
 d.ellipse((x-45*s,y-105*s,x+45*s,y+105*s),fill='#F5F6FA',outline='#4A5870',width=max(1,int(4*s)))
 d.polygon([(x-45*s,y+45*s),(x-88*s,y+88*s),(x-45*s,y+85*s)],fill='#FF607A'); d.polygon([(x+45*s,y+45*s),(x+88*s,y+88*s),(x+45*s,y+85*s)],fill='#FF607A')
 d.ellipse((x-23*s,y-50*s,x+23*s,y-4*s),fill='#55A9E8',outline='#355C84',width=max(1,int(3*s)))
 d.rectangle((x-14*s,y+72*s,x+14*s,y+100*s),fill='#FFD447')
 q=50+35*abs(math.sin(fl*9)); d.polygon([(x-20*s,y+95*s),(x+20*s,y+95*s),(x,y+95*s+q*s)],fill='#FF8E28'); d.polygon([(x-9*s,y+95*s),(x+9*s,y+95*s),(x,y+95*s+q*.65*s)],fill='#FFE15A')

def bg(d,t,scene):
 skies=['#73C9FF','#A8E6C1','#C8B6FF','#FFD98A','#72C7FF','#6697E7','#FFB5CE']; d.rectangle((0,0,W,H),fill=skies[scene])
 for k in range(5):
  x=((k*150+(-1 if k%2 else 1)*t*24)%700)-80; y=100+k*58; d.ellipse((x,y,x+100,y+45),fill='white'); d.ellipse((x+35,y-25,x+145,y+50),fill='white')
 rng=random.Random(900+scene)
 for i in range(24):
  x=rng.randrange(20,W-20); y=rng.randrange(260,690); r=2+int(2*abs(math.sin(t*5+i))); d.ellipse((x-r,y-r,x+r,y+r),fill='#FFF09A')
 d.ellipse((-190,650,370,1100),fill='#63BD79'); d.ellipse((170,625,760,1100),fill='#52AA68'); d.rectangle((0,790,W,H),fill='#52AA68')

def header(d):
 box(d,(18,18,W-18,100),22,'white','#536BFF',3); text(d,'चीकू का मजेदार मिशन',38,29,'#263B92'); box(d,(35,120,W-35,192),18,'white'); text(d,'उल्टी गिनती सीखो',138,27,'#E84F72')

def card(d,s):
 box(d,(22,812,W-22,932),25,'#172543'); size=29 if len(s)<25 else 19; text(d,s,850,size,'white')

def frame(scene,t):
 img=Image.new('RGB',(W,H)); d=ImageDraw.Draw(img); bg(d,t,scene); header(d); bounce=8*math.sin(t*5)
 if scene==0:
  rabbit(d,145,590,1.0,bounce); rocket(d,390,575,1.0,t); text(d,'रॉकेट तैयार है',270,40,'white',True,3,'#31507A')
  for i in range(10):
   x=70+(i%5)*95; y=390+(i//5)*55; text(d,'★',y if False else y,32,'#FFD447')
  card(d,'10')
 elif scene<5:
  rx=125+scene*35+55*math.sin(t*2); ry=585+12*math.sin(t*5); rabbit(d,rx,ry,1.0,bounce); rocket(d,390+18*math.sin(t*2.4),575,1.0,t)
  nums=['10   9   8','7   6   5','4   3   2','1'][scene-1]; text(d,nums,280,58,'white',True,2,'#30446D')
  vals=nums.split()
  for i,v in enumerate(vals):
   bx=110+i*160; by=410+28*math.sin(t*4+i); d.ellipse((bx-48,by-48,bx+48,by+48),fill='#FFEA72',outline='#D99A28',width=4); f=F(38,True); bb=d.textbbox((0,0),v,font=f); d.text((bx-(bb[2]-bb[0])/2,by-25),v,font=f,fill='#4C3A00')
  card(d,nums)
 elif scene==5:
  rx=120+62*t; ry=585-35*t+20*math.sin(t*3); rocket(d,rx,ry,1.0,t); rabbit(d,115,ry+10,0.85,10*math.sin(t*7)); text(d,'आसमान में गिनती',280,38,'white',True,3,'#31507A')
  for i,v in enumerate(range(10,0,-1)):
   x=(35+i*62+t*25)%575; y=385+(i*47%250); d.ellipse((x-21,y-21,x+21,y+21),fill='#FFE66D'); f=F(17,True); d.text((x-8,y-12),str(v),font=f,fill='#4B3C00')
  card(d,'10  9  8  7  6  5  4  3  2  1')
 else:
  rabbit(d,145,580,1.15,15*math.sin(t*7)); rocket(d,390,570,1.1,t); text(d,'उड़ान सफल',275,43,'white',True,3,'#9B3D62'); text(d,'10 → 9 → 8 → 7 → 6 → 5',350,23,'white'); text(d,'→ 4 → 3 → 2 → 1',392,27,'white')
  for i in range(18):
   x=(i*43+int(t*70))%W; y=460+int(55*math.sin(t*3+i)); d.text((x,y),'✦',font=F(24,True),fill='#FFE45E')
  card(d,'उल्टी गिनती = 10 से 1')
 return img

def music(path):
 sr=22050; notes=[523.25,659.25,783.99,659.25,587.33,698.46,880,698.46]; total=DURATION=56; out=[]
 for i in range(int(total*sr)):
  tt=i/sr; n=notes[int(tt*2)%len(notes)]; a=.025; v=a*math.sin(2*math.pi*n*tt)+.009*math.sin(4*math.pi*n*tt); out.append(int(v*32767))
 with wave.open(str(path),'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(b''.join(struct.pack('<h',x) for x in out))

def tts(text_,p): asyncio.run(edge_tts.Communicate(text=text_,voice='hi-IN-SwaraNeural',rate=TTS_RATE).save(str(p)))

def render_scene(scene,audio,out):
 cmd=['ffmpeg','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(audio),'-t',str(SEC),'-map','0:v','-map','1:a','-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-af','apad=pad_dur=8,atrim=0:8','-c:a','aac','-b:a','128k',str(out)]
 p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 for i in range(FPS*SEC): p.stdin.write(frame(scene,i/FPS).tobytes())
 p.stdin.close(); log=p.stdout.read(); rc=p.wait()
 if rc: raise RuntimeError(log.decode(errors='ignore')[-5000:])

def main():
 print('TOON KIDS STUDY DYNAMIC — no Gemini, no Kaggle, no video API')
 for p in WORK.glob('*'):
  if p.is_file(): p.unlink()
 scenes=[]
 for i,n in enumerate(STORY['narration']):
  a=WORK/f'a{i}.mp3'; v=WORK/f's{i}.mp4'; print(f'scene {i+1}/7'); tts(n,a); render_scene(i,a,v); scenes.append(v)
 c=WORK/'concat.txt'; c.write_text(''.join(f"file \'{p.resolve()}\'\n" for p in scenes),encoding='utf-8')
 m=WORK/'music.wav'; music(m); base=WORK/'base.mp4'
 subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(c),'-c','copy',str(base)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
 subprocess.run(['ffmpeg','-y','-i',str(base),'-i',str(m),'-filter_complex','[1:a]volume=0.30[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=1[a]','-map','0:v','-map','[a]','-vf','scale=1080:1920:flags=lanczos','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(OUT)],check=True)
 meta={'title':STORY['title'],'learning':STORY['learning'],'concept':STORY['concept'],'moral':STORY['moral'],'scene_count':7,'scene_seconds':8,'duration':56,'story_mode':'dynamic_cartoon_v3','video_generator':'pillow_frame_animation_ffmpeg_no_gpu','created_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
 META.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
 fp=hashlib.sha256(json.dumps(STORY,ensure_ascii=False,sort_keys=True).encode()).hexdigest(); hist=[]
 if HISTORY.exists():
  try: hist=json.loads(HISTORY.read_text(encoding='utf-8'))
  except: hist=[]
 hist.append({'title':STORY['title'],'learning':STORY['learning'],'fingerprint':fp}); HISTORY.write_text(json.dumps(hist[-50:],ensure_ascii=False,indent=2),encoding='utf-8')
 print('DONE',OUT,OUT.stat().st_size)
if __name__=='__main__': main()
