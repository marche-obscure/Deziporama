@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  python -m venv .venv || goto :err
  .venv\Scripts\pip install -r requirements.txt || goto :err
)
start "" .venv\Scripts\pythonw.exe app.py
exit /b 0
:err
echo Echec de l installation. & pause
