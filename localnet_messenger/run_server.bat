@echo off
REM LocalNet Messenger - Server Launcher for Windows
cd /d "%~dp0"
echo Starting LocalNet Messenger Server...
python server\server.py --host 0.0.0.0 --port 8765 %*
