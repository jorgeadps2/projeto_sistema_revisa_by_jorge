@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0Iniciar_Sistemas_Revisa.py"
  exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
  start "" py -3 "%~dp0Iniciar_Sistemas_Revisa.py"
  exit /b
)
echo Python nao foi encontrado. Instale Python 3 e marque a opcao Add Python to PATH.
pause
endlocal
