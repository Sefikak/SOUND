@echo off
rem SOUND Android'i emülatörde açar: emülatörü başlatır, son APK'yı kurar ve uygulamayı çalıştırır.
setlocal
set "SDK=%LOCALAPPDATA%\Android\Sdk"
set "ANDROID_AVD_HOME=%LOCALAPPDATA%\SOUNDtools\avd"
start "" "%SDK%\emulator\emulator.exe" -avd sound -no-snapshot-save
"%SDK%\platform-tools\adb.exe" wait-for-device
:bekle
for /f %%b in ('"%SDK%\platform-tools\adb.exe" shell getprop sys.boot_completed') do if "%%b"=="1" goto hazir
timeout /t 2 /nobreak >nul
goto bekle
:hazir
call "%~dp0build.bat" install
"%SDK%\platform-tools\adb.exe" shell am start -n com.sound.app/.MainActivity
