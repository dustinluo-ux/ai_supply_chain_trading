@echo off
REM Starts regime_watcher.py as a background process using the wealth conda env.
REM Run this manually or via Task Scheduler at system startup.

set PYTHON=C:\Users\dusro\anaconda3\envs\wealth\python.exe
set SCRIPT=%~dp0..\scripts\regime_watcher.py
set LOGFILE=%~dp0..\logs\regime_watcher.log

if not exist "%~dp0..\logs" mkdir "%~dp0..\logs"

echo [%date% %time%] Starting regime_watcher.py >> "%LOGFILE%"
start "regime_watcher" /B "%PYTHON%" "%SCRIPT%" >> "%LOGFILE%" 2>&1
echo [%date% %time%] regime_watcher.py launched (PID visible in Task Manager) >> "%LOGFILE%"
