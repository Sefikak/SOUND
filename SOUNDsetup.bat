<# : SOUND setup (batch + PowerShell)
:: SOUND kurulumu: bu dosyaya çift tıklaman yeterli.
@echo off
chcp 65001 >nul
set "SOUND_SETUP=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ([IO.File]::ReadAllText($env:SOUND_SETUP, [Text.Encoding]::UTF8))"
echo.
pause
exit /b
#>

# ---------------------------------------------------------------------------
# SOUND kurulumu
#  1. Python (3.10-3.13) ve Git yoksa winget ile kurar
#  2. https://github.com/Sefikak/SOUND deposunu Masaüstü\SOUND'a indirir (varsa günceller)
#  3. Uygulamaya ayrı bir Python ortamı (.venv) kurup paketleri yükler
#  4. Masaüstü ve Başlat menüsüne kısayol koyar, uygulamayı açar
# Tekrar çalıştırmak güvenlidir: kurulu olanı onarır/günceller, kitaplığa (data\) dokunmaz.
# ---------------------------------------------------------------------------
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'SOUND kurulumu'
$Repo = 'https://github.com/Sefikak/SOUND.git'

function Step($text) { Write-Host "`n>> $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "   $text" -ForegroundColor Green }
function Fail($text) { Write-Host "`nHATA: $text" -ForegroundColor Red; exit 1 }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Works($exe, [string[]]$arguments) {
    try { & $exe @arguments *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
}
function Winget-Install($id, [string[]]$extra) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "winget bulunamadı. Microsoft Store'dan 'Uygulama Yükleyici' (App Installer) uygulamasını güncelleyip tekrar dene."
    }
    & winget install -e --id $id --accept-package-agreements --accept-source-agreements @extra
    Refresh-Path
}

Write-Host '======================================' -ForegroundColor Magenta
Write-Host '            SOUND kurulumu            ' -ForegroundColor Magenta
Write-Host '======================================' -ForegroundColor Magenta

# ---------- Python ----------
Step 'Python denetleniyor'
$PyCheck = @('-c', 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)')
$Python = $null
foreach ($candidate in @('python', 'py', "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe")) {
    $arguments = if ($candidate -eq 'py') { @('-3.13') + $PyCheck } else { $PyCheck }
    if (Works $candidate $arguments) { $Python = $candidate; break }
}
if (-not $Python) {
    Step 'Python 3.13 kuruluyor (birkaç dakika sürebilir)'
    Winget-Install 'Python.Python.3.13' @('--scope', 'user', '--override', '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1')
    $Python = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
    if (-not (Works $Python $PyCheck)) { Fail 'Python kurulamadı. https://www.python.org adresinden Python 3.13 kurup tekrar dene.' }
}
$PyPrefix = if ($Python -eq 'py') { @('-3.13') } else { @() }
Ok ("Python hazır: " + (& $Python @PyPrefix --version))

# ---------- Git ----------
Step 'Git denetleniyor'
if (-not (Works 'git' @('--version'))) {
    Step 'Git kuruluyor (yönetici izni istenirse Evet de)'
    Winget-Install 'Git.Git' @('--silent')
    if (-not (Works 'git' @('--version'))) { $env:Path += ";$env:ProgramFiles\Git\cmd" }
    if (-not (Works 'git' @('--version'))) { Fail 'Git kurulamadı. https://git-scm.com adresinden kurup tekrar dene.' }
}
Ok (& git --version)

# ---------- Uygulama dosyaları ----------
$Test = [bool]$env:SOUND_SETUP_TEST_DIR  # yalnızca deneme için: başka klasöre kurar, Başlat menüsüne dokunmaz, açmaz
$Desktop = if ($Test) { $env:SOUND_SETUP_TEST_DIR } else { [Environment]::GetFolderPath('Desktop') }
$App = Join-Path $Desktop 'SOUND'
if (Test-Path (Join-Path $App '.git')) {
    Step "SOUND zaten var, güncelleniyor: $App"
    & git -C $App pull --ff-only
    if ($LASTEXITCODE -ne 0) { Write-Host '   Güncellenemedi; mevcut sürümle devam ediliyor.' -ForegroundColor Yellow }
} elseif (Test-Path $App) {
    Fail "Masaüstünde zaten 'SOUND' adlı bir klasör var ama SOUND kurulumu değil. Adını değiştirip tekrar dene."
} else {
    Step "SOUND indiriliyor: $App"
    & git clone $Repo $App
    if ($LASTEXITCODE -ne 0) { Fail 'İndirilemedi. İnternet bağlantını kontrol edip tekrar dene.' }
}
Ok 'Dosyalar hazır'

# ---------- Python ortamı ve paketler ----------
$Venv = Join-Path $App '.venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $VenvPy)) {
    Step 'Uygulamanın Python ortamı oluşturuluyor'
    & $Python @PyPrefix -m venv $Venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPy)) { Fail 'Python ortamı oluşturulamadı.' }
}
Step 'Gerekli paketler yükleniyor (ilk kurulumda birkaç dakika sürer)'
& $VenvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
& $VenvPy -m pip install -r (Join-Path $App 'requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail 'Paketler yüklenemedi. Yukarıdaki hata mesajına bak ya da kurulumu tekrar çalıştır.' }
Ok 'Paketler hazır'

# ---------- Kısayollar ----------
Step 'Kısayollar oluşturuluyor'
$Shell = New-Object -ComObject WScript.Shell
$StartMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'SOUND.lnk'
$links = if ($Test) { @(Join-Path $Desktop 'SOUND.lnk') } else { @((Join-Path $Desktop 'SOUND.lnk'), $StartMenu) }
foreach ($link in $links) {
    $shortcut = $Shell.CreateShortcut($link)
    $shortcut.TargetPath = "$env:WINDIR\System32\wscript.exe"
    $shortcut.Arguments = '"' + (Join-Path $App 'run.vbs') + '"'
    $shortcut.WorkingDirectory = $App
    $shortcut.IconLocation = (Join-Path $App 'assets\icon.ico')
    $shortcut.Description = 'SOUND'
    $shortcut.Save()
}
Ok 'Masaüstü ve Başlat menüsüne eklendi'

Step 'SOUND açılıyor'
if (-not $Test) { Start-Process "$env:WINDIR\System32\wscript.exe" -ArgumentList ('"' + (Join-Path $App 'run.vbs') + '"') -WorkingDirectory $App }
Write-Host "`nKurulum tamamlandı. Uygulama güncellemeleri kendiliğinden alacak." -ForegroundColor Green
