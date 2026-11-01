# SOUND kurulum adımları. SOUNDsetup.exe her adımı ayrı çağırır (sihirbazda durum yazısı güncellensin diye).
#   -Step   : net | webview | python | git | fetch | packages | stop
#   -App    : kurulum klasörü
#   -State  : adımlar arası bilgi dosyası (seçilen Python yolu)
#   -Msg    : hata olursa kullanıcıya gösterilecek açıklama buraya yazılır
#   -Log    : ayrıntılı kayıt
# Çıkış kodu 0 = başarılı.
param(
    [Parameter(Mandatory)][string]$Step,
    [Parameter(Mandatory)][string]$App,
    [string]$State = "$env:TEMP\SOUNDsetup.state",
    [string]$Msg = "$env:TEMP\SOUNDsetup.msg",
    [string]$Log = "$env:TEMP\SOUNDsetup.log"
)
$ErrorActionPreference = 'Stop'
$Repo = 'https://github.com/Sefikak/SOUND.git'

function Write-Log($text) { Add-Content -Path $Log -Value ("[{0:HH:mm:ss}] [{1}] {2}" -f (Get-Date), $Step, $text) -Encoding UTF8 }
function Fail($text) {
    Write-Log "HATA: $text"
    [IO.File]::WriteAllText($Msg, $text)  # BOM'suz UTF-8; kurulum programı böyle okuyor
    exit 1
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
# Komutu çalıştırır, çıktısını kayda yazar, çıkış kodunu döndürür
function Run($exe, [string[]]$arguments) {
    Write-Log "> $exe $($arguments -join ' ')"
    $ErrorActionPreference = 'Continue'  # stderr'e yazan programlar (git, pip) istisna sayılmasın
    try {
        $out = & $exe @arguments 2>&1 | ForEach-Object { "$_" }
        if ($out) { Add-Content -Path $Log -Value $out -Encoding UTF8 }
        return $LASTEXITCODE
    } catch {
        Write-Log $_.Exception.Message
        return 1
    }
}
function Works($exe, [string[]]$arguments) {
    $ErrorActionPreference = 'Continue'
    try { & $exe @arguments *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
}
function Need-Winget($what) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "$what kurulu değil ve otomatik kurmak için gereken winget bu bilgisayarda yok.`n`nMicrosoft Store'dan 'Uygulama Yükleyici' (App Installer) uygulamasını güncelle ya da $what'u elle kurup kurulumu tekrar çalıştır."
    }
}
function Winget-Install($id, [string[]]$extra) {
    $code = Run 'winget' (@('install', '-e', '--id', $id, '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity') + $extra)
    Refresh-Path
    return $code
}

Remove-Item -Path $Msg -ErrorAction SilentlyContinue
Write-Log "başladı (klasör: $App)"

switch ($Step) {

    'net' {
        try {
            Invoke-WebRequest -Uri 'https://github.com/Sefikak/SOUND' -Method Head -UseBasicParsing -TimeoutSec 20 | Out-Null
        } catch {
            Fail "GitHub'a bağlanılamadı. İnternet bağlantını kontrol edip tekrar dene.`n`n($($_.Exception.Message))"
        }
    }

    'webview' {
        # SOUND'un arayüzü Microsoft Edge WebView2 ile çalışır (Windows 11'de ve güncel Windows 10'da hazır gelir)
        $keys = @(
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
            'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
            'HKCU:\Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
        )
        $found = $keys | Where-Object { (Get-ItemProperty -Path $_ -Name pv -ErrorAction SilentlyContinue).pv -notin @($null, '', '0.0.0.0') }
        if ($found) { Write-Log 'WebView2 var'; break }
        Need-Winget 'Microsoft Edge WebView2'
        if ((Winget-Install 'Microsoft.EdgeWebView2Runtime' @('--silent')) -ne 0) {
            Fail "Microsoft Edge WebView2 kurulamadı. https://go.microsoft.com/fwlink/p/?LinkId=2124703 adresinden indirip kurduktan sonra tekrar dene."
        }
    }

    'python' {
        # 3.10-3.13 arası bir Python gerekir (paketlerin hepsi bu sürümlerde hazır geliyor)
        $check = @('-c', 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)')
        $userPy = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
        $python = $null
        foreach ($candidate in @($userPy, 'python', 'py')) {
            $arguments = if ($candidate -eq 'py') { @('-3.13') + $check } else { $check }
            if (Works $candidate $arguments) { $python = $candidate; break }
        }
        if (-not $python) {
            Need-Winget 'Python'
            Winget-Install 'Python.Python.3.13' @('--scope', 'user', '--override',
                '/quiet InstallAllUsers=0 InstallLauncherAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0') | Out-Null
            if (Works $userPy $check) { $python = $userPy }
            else { Fail "Python kurulamadı. https://www.python.org/downloads/ adresinden Python 3.13'ü kurup (kurarken 'Add python.exe to PATH' kutusunu işaretle) tekrar dene." }
        }
        # 'python' bir komut adıysa tam yolunu bul, venv bu yoldan kurulacak
        $full = if ($python -eq 'py') { (& py -3.13 -c 'import sys; print(sys.executable)') } else { (& $python -c 'import sys; print(sys.executable)') }
        Write-Log "Python: $full"
        Set-Content -Path $State -Value $full -Encoding UTF8
    }

    'git' {
        if (Works 'git' @('--version')) { Write-Log (& git --version); break }
        Need-Winget 'Git'
        # önce yalnızca bu kullanıcı için (yönetici izni gerekmez), olmazsa bilgisayar geneli (izin ister)
        if ((Winget-Install 'Git.Git' @('--scope', 'user', '--silent')) -ne 0) { Winget-Install 'Git.Git' @('--silent') | Out-Null }
        foreach ($dir in @("$env:ProgramFiles\Git\cmd", "$env:LOCALAPPDATA\Programs\Git\cmd")) {
            if (Test-Path "$dir\git.exe") { $env:Path += ";$dir" }
        }
        if (-not (Works 'git' @('--version'))) { Fail "Git kurulamadı. https://git-scm.com/download/win adresinden kurup tekrar dene." }
    }

    'fetch' {
        Refresh-Path
        foreach ($dir in @("$env:ProgramFiles\Git\cmd", "$env:LOCALAPPDATA\Programs\Git\cmd")) { if (Test-Path "$dir\git.exe") { $env:Path += ";$dir" } }
        New-Item -ItemType Directory -Force -Path $App | Out-Null
        if (-not (Test-Path (Join-Path $App '.git'))) {
            # klasörde kaldırıcı vb. dosyalar olabileceği için clone yerine init + fetch + checkout
            if ((Run 'git' @('-C', $App, 'init', '-q')) -ne 0) { Fail 'Klasörde git deposu oluşturulamadı.' }
            Run 'git' @('-C', $App, 'remote', 'add', 'origin', $Repo) | Out-Null
        }
        if ((Run 'git' @('-C', $App, 'fetch', '--quiet', 'origin', 'main')) -ne 0) {
            Fail "SOUND indirilemedi. İnternet bağlantını kontrol edip tekrar dene."
        }
        $hasHead = Works 'git' @('-C', $App, 'rev-parse', '--verify', '-q', 'HEAD')
        if (-not $hasHead) {
            if ((Run 'git' @('-C', $App, 'checkout', '-q', '-f', '-B', 'main', 'origin/main')) -ne 0) { Fail 'SOUND dosyaları çıkarılamadı.' }
        } else {
            # mevcut kurulum: yalnızca ileri sar; yerel değişiklik varsa dokunma
            if ((Run 'git' @('-C', $App, 'merge', '--ff-only', '-q', 'origin/main')) -ne 0) {
                Write-Log 'güncellenemedi (yerel değişiklik ya da ayrışma); mevcut sürümle devam'
            }
        }
        Run 'git' @('-C', $App, 'branch', '-q', '--set-upstream-to=origin/main', 'main') | Out-Null
        if (-not (Test-Path (Join-Path $App 'main.py'))) { Fail 'SOUND dosyaları eksik indi. Kurulumu tekrar çalıştır.' }
    }

    'packages' {
        $venv = Join-Path $App '.venv'
        $venvPy = Join-Path $venv 'Scripts\python.exe'
        if (-not (Test-Path $venvPy)) {
            $python = if (Test-Path $State) { (Get-Content $State -Encoding UTF8 | Select-Object -First 1).Trim() } else { 'python' }
            if ((Run $python @('-m', 'venv', $venv)) -ne 0 -or -not (Test-Path $venvPy)) { Fail 'Uygulamanın Python ortamı oluşturulamadı.' }
        }
        Run $venvPy @('-m', 'pip', 'install', '--upgrade', 'pip', '--quiet', '--disable-pip-version-check') | Out-Null
        if ((Run $venvPy @('-m', 'pip', 'install', '-r', (Join-Path $App 'requirements.txt'), '--disable-pip-version-check', '--no-input')) -ne 0) {
            Fail 'Gerekli paketler yüklenemedi. İnternet bağlantını kontrol edip kurulumu tekrar çalıştır.'
        }
        if (-not (Works $venvPy @('-c', 'import webview, yt_dlp, ytmusicapi'))) { Fail 'Paketler yüklendi ama çalışmıyor. Kurulumu tekrar çalıştır.' }
    }

    'stop' {
        # bu klasörden çalışan SOUND'u kapat (güncelleme ve kaldırma öncesi)
        $prefix = (Resolve-Path -LiteralPath $App -ErrorAction SilentlyContinue).Path
        if ($prefix) {
            Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
                Where-Object { $_.ExecutablePath -like "$prefix\*" -or $_.CommandLine -like "*$prefix*" } |
                ForEach-Object { Write-Log "kapatılıyor: $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        }
    }

    default { Fail "Bilinmeyen adım: $Step" }
}
Write-Log 'tamam'
exit 0
