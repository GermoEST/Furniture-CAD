@echo off
cd /d "%~dp0"
python Moobel.pyw
if errorlevel 1 pause
