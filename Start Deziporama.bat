@echo off
cd /d "%~dp0"
rem Reinstalls the dependencies as long as they cannot be imported (interrupted install, etc.).
.venv\Scripts\python.exe -c "import watchdog, send2trash, pystray, PIL" 2>nul && goto :run
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv 2>nul || python -m venv .venv || goto :err
)
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :err
:run
start "" .venv\Scripts\pythonw.exe app.py
exit /b 0
:err
echo Could not install the dependencies. Check the Internet connection, then try again.
pause
