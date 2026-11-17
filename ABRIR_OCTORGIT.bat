@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
where py >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale Python 3.11 ou superior em python.org.
  echo Durante a instalacao, habilite o Python Launcher.
  pause
  exit /b 1
)
py -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo Este programa precisa de Python 3.11 ou superior.
  pause
  exit /b 1
)
py -m octorgit.web %*
pause
