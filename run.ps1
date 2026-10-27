# Starts the app on http://127.0.0.1:8000 (localhost only, SR10).
# First run: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m uvicorn ccst.main:app --app-dir src --host 127.0.0.1 --port 8000
