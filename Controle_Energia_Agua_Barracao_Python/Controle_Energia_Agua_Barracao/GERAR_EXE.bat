@echo off
chcp 65001 >nul
title GERADOR - CONTROLE DE ENERGIA E AGUA
echo ==========================================
echo  CONTROLE DE ENERGIA E AGUA - BARRACAO
echo  Gerador do executavel Windows
echo ==========================================
py -m pip install --upgrade pip
py -m pip install pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "Controle_Energia_Agua" --icon "assets\imovel.ico" --add-data "assets\revisa_logo.jpeg;assets" --add-data "assets\imovel.png;assets" controle_energia_agua.py
if errorlevel 1 (
  echo.
  echo ERRO ao gerar o executavel. Confira se Python esta instalado.
  pause
  exit /b 1
)
echo.
echo Executavel criado em: dist\Controle_Energia_Agua.exe
pause
