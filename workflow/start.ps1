$ErrorActionPreference = 'Stop'
$workflowDir = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($commandName in @('py', 'node', 'npm', 'ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "Thiếu $commandName. Cài công cụ này rồi chạy lại."
    }
}

$venvPython = Join-Path $workflowDir 'work\.venv\Scripts\python.exe'
py -m venv (Join-Path $workflowDir 'work\.venv')
& $venvPython -m pip install -r (Join-Path $workflowDir 'requirements.txt')
Write-Host 'Mở http://127.0.0.1:8765 trên máy này. Nhấn Ctrl+C để dừng ứng dụng.'
& $venvPython -m uvicorn app:app --app-dir $workflowDir --host 127.0.0.1 --port 8765
