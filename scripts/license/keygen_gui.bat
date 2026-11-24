@echo off
cd /d "%~dp0..\.."
start "" ".venv\Scripts\pythonw.exe" scripts\license\keygen_gui.py
