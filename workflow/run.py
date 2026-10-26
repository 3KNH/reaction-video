"""Rebuild the Vietnamese reaction video from reviewed footage and script."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"
PROJECT = WORK / "project"
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
VOICE = CONFIG.get("voice", "giahuy")
os.environ.setdefault("HF_HOME", str(WORK / "hf-cache"))
os.environ.setdefault("HF_XET_CACHE", str(WORK / "hf-cache" / "xet"))
os.environ.setdefault("XDG_CACHE_HOME", str(WORK / "cache"))
os.environ.setdefault("XDG_CONFIG_HOME", str(WORK / "config"))
os.environ.setdefault("NPM_CONFIG_CACHE", str(WORK / "npm-cache"))
if Path("/usr/bin/chromium").exists():
    os.environ.setdefault("HYPERFRAMES_BROWSER_PATH", "/usr/bin/chromium")


def run(*args, cwd=None, env=None):
    subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)


def probe(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ]))


def prepare():
    PROJECT.mkdir(parents=True, exist_ok=True)
    assets = PROJECT / "assets"
    assets.mkdir(exist_ok=True)
    if not (PROJECT / "script.txt").exists():
        shutil.copy2(HERE / "example-script.txt", PROJECT / "script.txt")
    for name in ("build.py", "config.json", "DESIGN.md"):
        shutil.copy2(HERE / name, PROJECT / name)
    shutil.copy2(HERE / "tts.py", WORK / "tts.py")
    shutil.copy2(HERE / "project-package.json", PROJECT / "package.json")
    shutil.copy2(HERE / "package-lock.json", PROJECT / "package-lock.json")
    run("npm", "ci", "--ignore-scripts", "--no-audit", cwd=PROJECT)
    shutil.copy2(PROJECT / "node_modules/gsap/dist/gsap.min.js", assets / "gsap.min.js")
    inventory = []
    for alias, spec in CONFIG["sources"].items():
        source = HERE / "input" / spec["file"]
        if not source.is_file():
            raise FileNotFoundError(f"Missing source video: {source}")
        target = assets / f"{alias}.mp4"
        if "usable_seconds" in spec:
            run("ffmpeg", "-y", "-loglevel", "error", "-i", source,
                "-t", spec["usable_seconds"], "-an", "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "27", target)
        else:
            shutil.copy2(source, target)
        info = probe(target)
        inventory.append({"alias": alias, "file": spec["file"],
                          "duration": float(info["format"]["duration"]),
                          "size": int(info["format"]["size"])})
    (WORK / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2))
    print("Prepared", len(inventory), "clips. Review inventory.json and source footage before publishing.")


def synthesize():
    from huggingface_hub import snapshot_download
    from zerotts.hub import _ALLOW_PATTERNS
    model = WORK / "zerotts-model"
    if not (model / "config.json").exists():
        snapshot = snapshot_download("zeroweight-ai/ZeroTTS", allow_patterns=_ALLOW_PATTERNS)
        # ONNX external-data files must be beside their graphs, not HF cache symlinks.
        shutil.copytree(snapshot, model, symlinks=False, dirs_exist_ok=True)
    env = os.environ.copy()
    env["ZEROTTS_VOICE"] = VOICE
    run(sys.executable, WORK / "tts.py", env=env)


def review_sources():
    import numpy as np
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8",
                         download_root=str(WORK / "whisper-models"))
    results = []
    frames_dir = WORK / "review-frames"
    frames_dir.mkdir(exist_ok=True)
    for item in json.loads((WORK / "inventory.json").read_text()):
        name = item["alias"]
        source = HERE / "input" / item["file"]
        pcm = subprocess.check_output(["ffmpeg", "-loglevel", "error", "-i", str(source),
                                       "-ar", "16000", "-ac", "1", "-f", "s16le", "-"])
        audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        segments, info = model.transcribe(audio, beam_size=3, vad_filter=True)
        transcript = " ".join(s.text.strip() for s in segments)
        for i in range(6):
            point = item["duration"] * (i + 0.5) / 6
            run("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{point:.2f}",
                "-i", source, "-frames:v", "1", "-vf", "scale=240:-1",
                frames_dir / f"{name}-{i}.jpg")
        results.append({**item, "language": info.language, "transcript": transcript})
    (WORK / "source-transcripts.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    summary = WORK / "source-review.md"
    if not summary.exists():
        lines = ["# Clip review", "", "Check the six frames per clip and listen to its audio; ASR may be wrong.", ""]
        for item in results:
            lines += [f"## {item['alias']}", "", f"Source: {item['file']}",
                      f"Duration: {item['duration']:.1f}s", "Summary: TODO", "",
                      f"Automatic transcript: {item['transcript'] or '(none detected)'}", ""]
        summary.write_text("\n".join(lines), encoding="utf-8")
    print("Review", summary, "before choosing scenes or making factual claims")


def align():
    import numpy as np
    from faster_whisper import WhisperModel
    wav = WORK / f"narration-{VOICE}" / "narration.wav"
    pcm = subprocess.check_output(["ffmpeg", "-loglevel", "error", "-i", str(wav),
                                   "-ar", "16000", "-ac", "1", "-f", "s16le", "-"])
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    model = WhisperModel("base", device="cpu", compute_type="int8",
                         download_root=str(WORK / "whisper-models"))
    segments, _ = model.transcribe(audio, language="vi", beam_size=3,
                                   word_timestamps=True, vad_filter=False)
    result = [{"start": s.start, "end": s.end, "text": s.text,
               "words": [{"start": w.start, "end": w.end, "word": w.word}
                         for w in s.words or []]} for s in segments]
    target = WORK / f"narration-{VOICE}" / "asr-check.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    n_script = len((PROJECT / "script.txt").read_text().split())
    n_asr = sum(len(s["words"]) for s in result)
    if abs(n_asr - n_script) > n_script * 0.05:
        raise RuntimeError(f"ASR alignment mismatch: {n_asr} recognized vs {n_script} script words")
    print(f"Aligned {n_asr} words; review technical terms manually in {target}")


def compose():
    review = WORK / "source-review.md"
    if not review.exists() or "Summary: TODO" in review.read_text(encoding="utf-8"):
        raise RuntimeError("Review each source clip and fill work/source-review.md before composition")
    narrator = WORK / f"narration-{VOICE}"
    run("ffmpeg", "-y", "-loglevel", "error", "-i", narrator / "narration.wav",
        "-af", "volume=0.85", "-codec:a", "libmp3lame", "-b:a", "128k",
        PROJECT / "assets/narration.mp3")
    env = os.environ.copy()
    env["ZEROTTS_VOICE"] = VOICE
    run(sys.executable, PROJECT / "build.py", cwd=PROJECT, env=env)
    sections = json.loads((PROJECT / "timing.json").read_text())["sections"]
    out = PROJECT / "assets/sections"
    out.mkdir(exist_ok=True)
    for i, section in enumerate(sections):
        run("ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1",
            "-i", PROJECT / "assets" / f"{section['source']}.mp4", "-t", section["duration"],
            "-vf", "fps=24,scale=720:1280", "-c:v", "libx264",
            "-preset", "ultrafast", "-crf", "27", "-an", out / f"section-{i}.mp4")
    run("npx", "hyperframes", "lint", ".", cwd=PROJECT)
    run("npx", "hyperframes", "validate", ".", "--no-contrast", cwd=PROJECT)
    run("npx", "hyperframes", "inspect", ".", "--samples", "20", cwd=PROJECT)


def render():
    final = WORK / "final.mp4"
    duration = json.loads((PROJECT / "timing.json").read_text())["total"]
    if duration > 180:
        print(f"Note: {duration:.1f}s exceeds a 3-minute Short. Shorten the script and rerun TTS for that target.")
    run("npx", "hyperframes", "render", ".", "--output", final,
        "--fps", "24", "--quality", "standard", "--workers", "4", cwd=PROJECT)
    streams = probe(final)["streams"]
    if not {"audio", "video"}.issubset({s["codec_type"] for s in streams}):
        raise RuntimeError("Rendered file is missing audio or video")
    run("ffmpeg", "-y", "-loglevel", "error", "-i", final,
        "-c:v", "libx264", "-preset", "medium", "-crf", "27",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        WORK / "final-download.mp4")
    print("Download-ready output:", WORK / "final-download.mp4")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "review", "tts", "align", "compose", "render", "all"])
    stage = parser.parse_args().stage
    steps = [("prepare", prepare), ("review", review_sources), ("tts", synthesize), ("align", align),
             ("compose", compose), ("render", render)]
    for name, fn in steps:
        if stage in ("all", name):
            print("==", name, "==", flush=True)
            fn()


if __name__ == "__main__":
    main()
