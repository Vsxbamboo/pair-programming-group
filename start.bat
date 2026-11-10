@echo off
REM Double-click to start the drink machine. Example: start.bat --real all
cd /d "%~dp0"
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
if exist .venv\bin\python.exe set PY=.venv\bin\python.exe
%PY% run.py --open %*
pause
