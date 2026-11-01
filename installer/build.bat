@echo off
:: SOUNDsetup.exe derler (Inno Setup 6.7+ gerekir: winget install JRSoftware.InnoSetup)
cd /d "%~dp0"
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (echo Inno Setup bulunamadi & exit /b 1)
"%ISCC%" /Q SOUND.iss
