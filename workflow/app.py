"""Local web UI for the reaction-video workflow. Run with uvicorn on 127.0.0.1."""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from starlette.datastructures import UploadFile

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"
INPUT = HERE / "input"
PROJECT = WORK / "project"
BASE_CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
CONFIG_FILE = WORK / "config.json"
VOICES = {"giahuy", "huuduc", "quangminh", "tiendat"}
LOCK = threading.Lock()
JOB = {"running": False, "phase": "idle", "error": "", "finished": None}
LOG = WORK / "app.log"
app = FastAPI(title="Reaction Video Studio")


def config():
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else BASE_CONFIG


def active():
    with LOCK:
        return JOB["running"]


def script_text():
    path = PROJECT / "script.txt"
    return path.read_text(encoding="utf-8") if path.exists() else (HERE / "example-script.txt").read_text(encoding="utf-8")


def result_is_current():
    result = WORK / "final-download.mp4"
    if not result.exists():
        return False
    dependencies = [CONFIG_FILE, PROJECT / "script.txt", *INPUT.glob("*.mp4")]
    return all(not dep.exists() or dep.stat().st_mtime <= result.stat().st_mtime for dep in dependencies)


def run_job(stages):
    try:
        WORK.mkdir(exist_ok=True)
        with LOG.open("w", encoding="utf-8") as log:
            for stage in stages:
                with LOCK:
                    JOB["phase"] = stage
                log.write(f"\n=== {stage} ===\n")
                log.flush()
                process = subprocess.run([sys.executable, str(HERE / "run.py"), stage],
                                         cwd=HERE.parent, stdout=log, stderr=subprocess.STDOUT)
                if process.returncode:
                    raise RuntimeError(f"Bước {stage} thất bại. Xem nhật ký bên dưới.")
        with LOCK:
            JOB.update(running=False, phase="done", error="", finished=time.time())
    except Exception as exc:
        with LOCK:
            JOB.update(running=False, phase="failed", error=str(exc), finished=time.time())


def start(stages):
    with LOCK:
        if JOB["running"]:
            raise HTTPException(409, "Một tác vụ đang chạy")
        JOB.update(running=True, phase=stages[0], error="", finished=None)
    threading.Thread(target=run_job, args=(stages,), daemon=True).start()
    return {"started": stages}


@app.get("/", response_class=HTMLResponse)
def home():
    return (HERE / "app.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status():
    WORK.mkdir(exist_ok=True)
    cfg = config()
    files = {alias: (INPUT / spec["file"]).exists() for alias, spec in cfg["sources"].items()}
    review_path = WORK / "review.json"
    transcripts_path = WORK / "source-transcripts.json"
    transcript_list = json.loads(transcripts_path.read_text()) if transcripts_path.exists() else []
    review = json.loads(review_path.read_text()) if review_path.exists() else {}
    with LOCK:
        job = JOB.copy()
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-50:] if LOG.exists() else []
    return {"config": cfg, "script": script_text(), "files": files,
            "review": review, "transcripts": transcript_list, "job": job,
            "log": "\n".join(lines), "result_ready": result_is_current()}


@app.post("/api/save")
async def save(request: Request):
    if active():
        raise HTTPException(409, "Chờ tác vụ hiện tại hoàn tất")
    form = await request.form()
    try:
        proposed = json.loads(str(form["config"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, "Cấu hình không hợp lệ") from exc
    if set(proposed.get("sources", {})) != set(BASE_CONFIG["sources"]):
        raise HTTPException(400, "Danh sách nguồn không hợp lệ")
    proposed["sources"] = BASE_CONFIG["sources"]
    aliases = set(BASE_CONFIG["sources"])
    if len(proposed.get("sections", [])) != len(BASE_CONFIG["sections"]):
        raise HTTPException(400, "Cần đủ bảy cảnh")
    for section in proposed["sections"]:
        if section.get("source") not in aliases or not section.get("title", "").strip():
            raise HTTPException(400, "Tên cảnh hoặc nguồn cảnh không hợp lệ")
    if proposed.get("voice") not in VOICES:
        raise HTTPException(400, "Vui lòng chọn một giọng nam có sẵn")
    title = str(proposed.get("title", "")).strip()
    proposed["title"] = title
    text = str(form.get("script", "")).strip()
    if not title or len(title) > 160 or not text or len(text) > 50000:
        raise HTTPException(400, "Tiêu đề hoặc kịch bản không hợp lệ")
    if len([p for p in text.split("\n\n") if p.strip()]) != len(proposed["sections"]):
        raise HTTPException(400, "Kịch bản cần bảy đoạn, mỗi đoạn ứng với một cảnh")
    WORK.mkdir(exist_ok=True)
    PROJECT.mkdir(exist_ok=True)
    INPUT.mkdir(exist_ok=True)
    uploaded_any = False
    for alias, spec in BASE_CONFIG["sources"].items():
        incoming = form.get("file_" + alias)
        if isinstance(incoming, UploadFile) and incoming.filename:
            target = INPUT / spec["file"]
            temp = target.with_suffix(".uploading")
            with temp.open("wb") as destination:
                while chunk := await incoming.read(1024 * 1024):
                    destination.write(chunk)
            temp.replace(target)
            uploaded_any = True
    if not CONFIG_FILE.exists() or json.loads(CONFIG_FILE.read_text(encoding="utf-8")) != proposed:
        CONFIG_FILE.write_text(json.dumps(proposed, ensure_ascii=False, indent=2), encoding="utf-8")
    script_file = PROJECT / "script.txt"
    if not script_file.exists() or script_file.read_text(encoding="utf-8").strip() != text:
        script_file.write_text(text + "\n", encoding="utf-8")
    if uploaded_any:
        for path in (WORK / "review.json", WORK / "source-review.md", WORK / "source-transcripts.json"):
            path.unlink(missing_ok=True)
    return {"saved": True}


@app.post("/api/analyze")
def analyze():
    cfg = config()
    missing = [spec["file"] for spec in cfg["sources"].values()
               if not (INPUT / spec["file"]).is_file()]
    if missing:
        raise HTTPException(400, "Thiếu clip: " + ", ".join(missing))
    return start(["prepare", "review"])


@app.post("/api/review")
async def save_review(request: Request):
    if active():
        raise HTTPException(409, "Chờ tác vụ hiện tại hoàn tất")
    summaries = await request.json()
    aliases = list(BASE_CONFIG["sources"])
    if not isinstance(summaries, dict) or set(summaries) != set(aliases):
        raise HTTPException(400, "Cần tóm tắt đủ sáu clip")
    for alias in aliases:
        value = summaries[alias]
        if not isinstance(value, str) or len(value.strip()) < 8 or "TODO" in value.upper():
            raise HTTPException(400, f"Kiểm tra tóm tắt của {alias}")
    transcripts_path = WORK / "source-transcripts.json"
    if not transcripts_path.exists():
        raise HTTPException(400, "Hãy phân tích clip trước")
    transcripts = {item["alias"]: item for item in json.loads(transcripts_path.read_text())}
    lines = ["# Đã duyệt nguồn", ""]
    for alias in aliases:
        item = transcripts[alias]
        lines += [f"## {alias}", "", f"Source: {item['file']}",
                  f"Summary: {summaries[alias].strip()}", "",
                  f"Automatic transcript: {item['transcript'] or '(none detected)'}", ""]
    (WORK / "source-review.md").write_text("\n".join(lines), encoding="utf-8")
    (WORK / "review.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True}


@app.post("/api/generate")
def generate():
    if not (WORK / "review.json").exists():
        raise HTTPException(400, "Duyệt và lưu tóm tắt clip trước khi tạo video")
    return start(["tts", "align", "compose", "render"])


@app.get("/frames/{alias}/{index}")
def frame(alias: str, index: int):
    if alias not in BASE_CONFIG["sources"] or index not in range(6):
        raise HTTPException(404)
    path = WORK / "review-frames" / f"{alias}-{index}.jpg"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


@app.get("/source/{alias}")
def source_video(alias: str):
    if alias not in BASE_CONFIG["sources"]:
        raise HTTPException(404)
    path = INPUT / BASE_CONFIG["sources"][alias]["file"]
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="video/mp4")


@app.get("/video")
def video():
    if not result_is_current():
        raise HTTPException(404)
    return FileResponse(WORK / "final-download.mp4", media_type="video/mp4")


@app.get("/download")
def download():
    if not result_is_current():
        raise HTTPException(404)
    return FileResponse(WORK / "final-download.mp4", media_type="video/mp4",
                        filename="reaction-video.mp4")


@app.get("/download-audio")
def download_audio():
    path = PROJECT / "assets" / "narration.mp3"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg", filename="loi-binh.mp3")
