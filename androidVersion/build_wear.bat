@echo off
rem SOUND Galaxy Watch uygulamasi: build_wear.bat [install^|release]  (install: bagli saate/emulatore kurar)
setlocal
set "JAVA_HOME="
for /d %%d in ("%LOCALAPPDATA%\SOUNDtools\jdk\*") do set "JAVA_HOME=%%d"
set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "TASK=:wear:assembleDebug"
if /i "%~1"=="install" set "TASK=:wear:installDebug"
if /i "%~1"=="release" set "TASK=:wear:assembleRelease"
call "%~dp0gradlew.bat" --project-cache-dir "%LOCALAPPDATA%\SOUNDbuild\gradle-cache" %TASK%
