@echo off
cd /d "%~dp0"
echo Paigaldan vajalikud Pythoni moodulid (see votab paar minutit)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Valmis! Kaivita programm: Moobel.pyw (topeltklikk) voi kaivita.bat
pause
