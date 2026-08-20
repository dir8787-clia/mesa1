@echo off
REM LocalNet Messenger - Client Launcher for Windows
cd /d "%~dp0"
echo Starting LocalNet Messenger Client...
python client\client.py %*
