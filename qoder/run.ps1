$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
$env:PYTHONUTF8 = "1"
& ".venv\Scripts\python.exe" run.py
