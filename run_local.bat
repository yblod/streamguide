@echo off
rem Startet die Add-on-Version lokal auf dem PC zum Testen (Port 8766, Daten in .\data).
rem Die PC-Version in F:\Claude\streamguide bleibt davon unberührt.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Erstelle virtuelle Umgebung ...
  py -3.10 -m venv .venv
  .venv\Scripts\python -m pip install -q -r streamguide\requirements.txt
)
set STREAMGUIDE_DATA_DIR=%~dp0data
set STREAMGUIDE_PORT=8766
set STREAMGUIDE_HOST=127.0.0.1
if exist .env (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set %%a=%%b
)
.venv\Scripts\python streamguide\run.py %*
