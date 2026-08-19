@echo off
setlocal
cd /d %~dp0
rem Python 3.14 on Windows needs PYTHONCASEOK for case-insensitive imports
rem (the PyInstaller package dir has mixed case). Harmless on other versions.
set PYTHONCASEOK=1

if not exist .venv (
    echo Creating .venv ...
    python -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip || exit /b 1
pip install -r requirements.txt -r requirements-tray.txt || exit /b 1

echo Running smoke test ...
python tray.py --smoke || exit /b 1

echo Writing build info ...
python -c "import json,subprocess,datetime;r=subprocess.run(['git','rev-parse','--short=9','HEAD'],capture_output=True,text=True);json.dump({'sha':r.stdout.strip() or 'unknown','date':datetime.datetime.now().astimezone().isoformat(timespec='seconds')},open('backend/_buildinfo.json','w'))" || exit /b 1

echo Building dist\llama-monitor.exe ...
pyinstaller --noconfirm --onefile --noconsole --name llama-monitor --icon assets\tray\icon.ico --add-data "frontend;frontend" --add-data "config.example.json;." --add-data "backend/_buildinfo.json;backend" --add-data "assets/tray;assets/tray" --hidden-import pystray._win32 --hidden-import six --hidden-import uvicorn.loops.auto --hidden-import uvicorn.loops.asyncio --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.protocols.websockets.wsproto_impl --hidden-import uvicorn.protocols.websockets.websockets_impl --hidden-import websockets --hidden-import wsproto tray.py || exit /b 1

echo.
echo Done: dist\llama-monitor.exe
endlocal
