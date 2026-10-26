"""Generate Vietnamese narration from the approved script with ZeroTTS."""

import json
import os
from pathlib import Path

from zerotts import ZeroTTS
from zerotts.audio import concat_with_silence
from zerotts.chunking import chunk_text, clean_segment_punctuation, normalize_punctuation

ROOT = Path(__file__).parent
SCRIPT = ROOT / "project" / "script.txt"
VOICE = os.environ.get("ZEROTTS_VOICE", "giahuy")
OUT = ROOT / f"narration-{VOICE}"
OUT.mkdir(exist_ok=True)

text = SCRIPT.read_text(encoding="utf-8")
segments = [
    clean_segment_punctuation(segment)
    for segment in chunk_text(normalize_punctuation(text), max_chunk_sec=15.0)
]
segments = [segment for segment in segments if segment]

tts = ZeroTTS.from_pretrained(str(ROOT / "zerotts-model"))
audio_chunks = []
timing = []
cursor = 0.0
for index, segment in enumerate(segments):
    audio = tts.synthesize(segment, voice=VOICE)
    duration = audio.shape[-1] / tts.sample_rate
    tts.save_audio(audio, str(OUT / f"segment-{index:02d}.wav"))
    timing.append({"text": segment, "start": cursor, "end": cursor + duration})
    audio_chunks.append(audio)
    cursor += duration + 0.15

joined = concat_with_silence(audio_chunks, silence_sec=0.15, sample_rate=tts.sample_rate)
tts.save_audio(joined, str(OUT / "narration.wav"))
(OUT / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {len(timing)} segments, {joined.shape[-1] / tts.sample_rate:.1f}s")
