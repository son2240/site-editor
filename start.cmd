@echo off
rem Open the site editor. Drag a site folder onto this file to open that folder directly.
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required: https://www.python.org/downloads/
  pause
  exit /b 1
)
if "%~1"=="" (
  start "" pythonw "%~dp0launcher.py"
) else (
  start "" pythonw "%~dp0editor.py" --site "%~1"
)
