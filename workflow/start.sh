#!/usr/bin/env bash
set -euo pipefail

workflow_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for command_name in python3 node npm ffmpeg ffprobe; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Thiếu $command_name. Cài công cụ này rồi chạy lại." >&2
    exit 1
  fi
done

python3 -m venv "$workflow_dir/work/.venv"
"$workflow_dir/work/.venv/bin/python" -m pip install -r "$workflow_dir/requirements.txt"
echo "Mở http://127.0.0.1:8765 trên máy này. Nhấn Ctrl+C để dừng ứng dụng."
exec "$workflow_dir/work/.venv/bin/python" -m uvicorn app:app --app-dir "$workflow_dir" --host 127.0.0.1 --port 8765
