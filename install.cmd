@echo off
rem One-time setup: desktop + Start menu shortcuts, then open the editor.
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required: https://www.python.org/downloads/
  pause
  exit /b 1
)
python "%~dp0launcher.py" --install
if errorlevel 1 (
  pause
  exit /b 1
)
start "" pythonw "%~dp0launcher.py"
