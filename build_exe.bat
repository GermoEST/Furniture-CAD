@echo off
rem Ehitab Moobel.exe (kaust dist\Moobel). Vajab, et install.bat oleks enne kaivitatud.
cd /d "%~dp0"
echo Paigaldan PyInstalleri...
python -m pip install --upgrade pyinstaller
echo.
echo Ehitan programmi (votab 3-10 minutit)...
python -m PyInstaller --noconfirm --clean --windowed --name Moobel --icon moobel.ico --collect-submodules moobel --collect-data pyvista --collect-submodules pyvistaqt --collect-submodules vtkmodules --collect-all manifold3d --collect-data trimesh --hidden-import mapbox_earcut --hidden-import shapely --exclude-module mypy --exclude-module pytest --exclude-module IPython --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module tkinter Moobel.pyw
if errorlevel 1 goto viga
if exist mesa xcopy /E /I /Y mesa dist\Moobel\mesa >nul
copy /Y LOEMIND.txt dist\Moobel\ >nul
copy /Y kaivita_tarkvara.bat dist\Moobel\ >nul
echo.
echo VALMIS: dist\Moobel\Moobel.exe
echo Teistele andmiseks paki kogu kaust dist\Moobel ZIP-iks.
explorer dist\Moobel
pause
exit /b 0
:viga
echo.
echo Ehitamine ebaonnestus - vaata ylalolevaid teateid.
pause
