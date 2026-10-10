@echo off
cd /d "%~dp0"
rem Reinstalle les dependances tant qu'elles ne sont pas importables (installation interrompue, etc.).
.venv\Scripts\python.exe -c "import watchdog, send2trash" 2>nul && goto :run
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv 2>nul || python -m venv .venv || goto :err
)
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :err
:run
start "" .venv\Scripts\pythonw.exe app.py
exit /b 0
:err
echo Echec de l'installation des dependances. Verifiez la connexion Internet puis relancez.
pause
