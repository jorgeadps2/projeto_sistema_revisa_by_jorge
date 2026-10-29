@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0FolhaPagamentoRevisa_1_140.exe" (
  "%~dp0FolhaPagamentoRevisa_1_140.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_139.exe" (
  "%~dp0FolhaPagamentoRevisa_1_139.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_138.exe" (
  "%~dp0FolhaPagamentoRevisa_1_138.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_137.exe" (
  "%~dp0FolhaPagamentoRevisa_1_137.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_136.exe" (
  "%~dp0FolhaPagamentoRevisa_1_136.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_135.exe" (
  "%~dp0FolhaPagamentoRevisa_1_135.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_134.exe" (
  "%~dp0FolhaPagamentoRevisa_1_134.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_133.exe" (
  "%~dp0FolhaPagamentoRevisa_1_133.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_132.exe" (
  "%~dp0FolhaPagamentoRevisa_1_132.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_131.exe" (
  "%~dp0FolhaPagamentoRevisa_1_131.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_130.exe" (
  "%~dp0FolhaPagamentoRevisa_1_130.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_129.exe" (
  "%~dp0FolhaPagamentoRevisa_1_129.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_128.exe" (
  "%~dp0FolhaPagamentoRevisa_1_128.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_127.exe" (
  "%~dp0FolhaPagamentoRevisa_1_127.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_126.exe" (
  "%~dp0FolhaPagamentoRevisa_1_126.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_125.exe" (
  "%~dp0FolhaPagamentoRevisa_1_125.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_124.exe" (
  "%~dp0FolhaPagamentoRevisa_1_124.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_123.exe" (
  "%~dp0FolhaPagamentoRevisa_1_123.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_122.exe" (
  "%~dp0FolhaPagamentoRevisa_1_122.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_121.exe" (
  "%~dp0FolhaPagamentoRevisa_1_121.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_112.exe" (
  "%~dp0FolhaPagamentoRevisa_1_112.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_111.exe" (
  "%~dp0FolhaPagamentoRevisa_1_111.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_110.exe" (
  "%~dp0FolhaPagamentoRevisa_1_110.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_109.exe" (
  "%~dp0FolhaPagamentoRevisa_1_109.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_52.exe" (
  "%~dp0FolhaPagamentoRevisa_1_52.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_51.exe" (
  "%~dp0FolhaPagamentoRevisa_1_51.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_50.exe" (
  "%~dp0FolhaPagamentoRevisa_1_50.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_49.exe" (
  "%~dp0FolhaPagamentoRevisa_1_49.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_48.exe" (
  "%~dp0FolhaPagamentoRevisa_1_48.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_47.exe" (
  "%~dp0FolhaPagamentoRevisa_1_47.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_46.exe" (
  "%~dp0FolhaPagamentoRevisa_1_46.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_45.exe" (
  "%~dp0FolhaPagamentoRevisa_1_45.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_44.exe" (
  "%~dp0FolhaPagamentoRevisa_1_44.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_43.exe" (
  "%~dp0FolhaPagamentoRevisa_1_43.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_42.exe" (
  "%~dp0FolhaPagamentoRevisa_1_42.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa_1_41.exe" (
  "%~dp0FolhaPagamentoRevisa_1_41.exe"
  exit /b
)
if exist "%~dp0FolhaPagamentoRevisa.exe" (
  "%~dp0FolhaPagamentoRevisa.exe"
  exit /b
)
where py >nul 2>nul
if errorlevel 1 (
  echo Python nao foi encontrado. Instale Python 3.11 ou superior e marque a opcao Add Python to PATH.
  pause
  exit /b 1
)
py -3 folha_pagamento.py
if errorlevel 1 pause
endlocal
