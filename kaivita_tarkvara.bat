@echo off
rem Kasuta seda, kui 3D vaade jaab mustaks/tyhjaks (vana videokaart, kaugtoolaud)
cd /d "%~dp0"
set MOOBEL_GL=sw
python Moobel.pyw
if errorlevel 1 pause
