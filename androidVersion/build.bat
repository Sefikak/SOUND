@echo off
rem SOUND Android: APK derler ve (emülatör/telefon bağlıysa) kurar. Kullanım: build.bat [install^|release]
setlocal
set "JAVA_HOME="
for /d %%d in ("%LOCALAPPDATA%\SOUNDtools\jdk\*") do set "JAVA_HOME=%%d"
set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "TASK=assembleDebug"
if /i "%~1"=="install" set "TASK=installDebug"
if /i "%~1"=="release" set "TASK=assembleRelease"
call "%~dp0gradlew.bat" --project-cache-dir "%LOCALAPPDATA%\SOUNDbuild\gradle-cache" %TASK%
