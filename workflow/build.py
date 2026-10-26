from pathlib import Path
from html import escape
import json
import os
import wave

root = Path(__file__).parent
sections = [p.strip() for p in (root / 'script.txt').read_text().split('\n\n') if p.strip()]
config = json.loads((root / 'config.json').read_text())
names = [section['title'] for section in config['sections']]
media = [section['source'] for section in config['sections']]
if len(sections) != len(names):
    raise ValueError('Each script paragraph needs exactly one section in config.json')
words = [w for section in sections for w in section.split()]
voice = os.environ.get('ZEROTTS_VOICE', 'giahuy')
narration_dir = root.parent / f'narration-{voice}'
asr = json.loads((narration_dir / 'asr-check.json').read_text())
spoken = [w for segment in asr for w in segment['words']]
with wave.open(str(narration_dir / 'narration.wav')) as wav:
    audio_duration = wav.getnframes() / wav.getframerate()

def time_at(index):
    if index >= len(words):
        return audio_duration
    scaled = round(index * (len(spoken)-1) / (len(words)-1))
    return max(0.0, spoken[scaled]['start'])

def duration_to(index):
    if index >= len(words):
        return audio_duration
    return time_at(index)

clips=[]; cues=[]; titles=[]; cursor=0; section_info=[]
for j,section in enumerate(sections):
    count=len(section.split())
    start=time_at(cursor)
    end=duration_to(cursor+count)
    duration=end-start
    section_info.append({'title':names[j],'source':media[j],'start':start,'duration':duration})
    clips.append(f'<video class="clip" id="video-{j}" data-start="{start:.2f}" data-duration="{duration:.2f}" data-track-index="0" src="assets/sections/section-{j}.mp4" muted playsinline></video>')
    titles.append(f'<div id="section-{j}" class="section clip" data-start="{start:.2f}" data-duration="3.4" data-track-index="2"><span>{names[j]}</span></div>')
    parts=section.split()
    for k in range(0,len(parts),4):
        begin=time_at(cursor+k)
        finish=duration_to(cursor+min(k+4,len(parts)))
        if finish<=begin: finish=begin+0.2
        label=escape(' '.join(parts[k:k+4]))
        cues.append(f'<div id="cue-{j}-{k//4}" class="cue clip" data-start="{begin:.2f}" data-duration="{finish-begin:.2f}" data-track-index="3"><span>{label}</span></div>')
    cursor+=count

html=f'''<!doctype html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=720, height=1280"><script src="assets/gsap.min.js"></script><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:720px;height:1280px;overflow:hidden;background:#F8F4EC}}#root{{position:relative;width:720px;height:1280px;overflow:hidden;font-family:Arial,sans-serif;color:#20251F}}
video{{position:absolute;inset:0;width:720px;height:1280px;object-fit:cover;z-index:0}}#shade{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.25),transparent 31%,transparent 58%,rgba(0,0,0,.69));z-index:1;pointer-events:none}}
.top{{position:absolute;top:72px;left:52px;right:52px;z-index:5;color:#fff;font-size:23px;font-weight:900;letter-spacing:.02em;text-shadow:0 2px 8px #222}}
.stamp{{position:absolute;top:117px;left:52px;z-index:5;color:#fff;font-size:20px;background:#B45836;padding:7px 12px;border-radius:5px}}
.section{{position:absolute;top:185px;left:52px;right:52px;z-index:4;display:flex}}.section span{{background:#F8F4EC;color:#20251F;padding:15px 20px;font-family:Georgia,serif;font-size:36px;font-weight:bold;max-width:616px;line-height:1.15;border-left:8px solid #B45836}}
.cue{{position:absolute;left:52px;right:52px;bottom:238px;z-index:6;display:flex;justify-content:center;align-items:center;min-height:88px;text-align:center}}.cue span{{display:inline-block;background:rgba(18,20,18,.89);border-radius:9px;padding:13px 20px;color:#fff;font-size:46px;line-height:1.12;font-weight:900;text-shadow:0 2px 3px #111;max-width:616px}}
.bottom{{position:absolute;bottom:75px;left:52px;right:52px;z-index:5;color:#fff;font-size:19px;line-height:1.2;text-shadow:0 2px 8px #111}}.flash{{position:absolute;inset:0;z-index:8;background:#F8F4EC;opacity:0;pointer-events:none}}
</style></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="{audio_duration}" data-width="720" data-height="1280">
{''.join(clips)}<audio class="clip" id="narration" data-start="0" data-duration="{audio_duration}" data-track-index="4" data-volume="0.85" src="assets/narration.mp3"></audio><div id="shade"></div><div class="top">{escape(config['title'].upper())}</div><div class="stamp">Tư liệu minh họa</div>{''.join(titles)}{''.join(cues)}<div class="bottom">Lời bình AI • Hình từ nhiều công trình</div><div id="flash" class="flash"></div></div>
<script>const tl=gsap.timeline({{paused:true}});window.__timelines['main']=tl;
for(const el of document.querySelectorAll('.section'))tl.from('#'+el.id,{{y:35,opacity:0,duration:.45,ease:'power3.out'}},Number(el.dataset.start)+.1);
for(const el of document.querySelectorAll('.cue'))tl.from('#'+el.id,{{y:18,opacity:0,duration:.14,ease:'power2.out'}},Number(el.dataset.start)+.02);
{''.join(f"tl.fromTo('#flash',{{opacity:0}},{{opacity:.8,duration:.16,yoyo:true,repeat:1,ease:'power1.inOut',immediateRender:false}},{s['start']-0.16:.2f});" for s in section_info[1:])}
</script></body></html>'''
(root/'index.html').write_text(html)
(root/'timing.json').write_text(json.dumps({'total':audio_duration,'sections':section_info},ensure_ascii=False,indent=2))
print(f'{len(cues)} captions across {audio_duration}s')
