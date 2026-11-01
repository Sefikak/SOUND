; SOUND kurulum sihirbazı (Inno Setup 6.7+)
; Derlemek için: installer\build.bat  →  depo kökünde SOUNDsetup.exe oluşur.
;
; Kurulum uygulama dosyalarını içinde taşımaz: seçilen klasöre GitHub'dan git ile indirir.
; Böylece uygulama kendi kendini güncelleyebilir (selfupdate.py) ve kurulum dosyası hiç eskimez.
; Asıl iş installer\steps.ps1'de; burada sihirbaz, denetimler ve kaldırma var.

#define AppName "SOUND"
#define AppURL "https://github.com/Sefikak/SOUND"

[Setup]
AppId={{6F1C2A9E-5B7D-4E3A-9C21-8D4F0B6A7E55}
AppName={#AppName}
AppVersion=1.0
AppVerName={#AppName}
AppPublisher=Sefikak
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}
VersionInfoDescription=SOUND kurulumu
; uygulama kendi klasörüne yazıyor (kitaplık, güncellemeler), bu yüzden kullanıcının yazabildiği bir yer
DefaultDirName={userpf}\{#AppName}
PrivilegesRequired=lowest
UsePreviousAppDir=yes
AppendDefaultDirName=yes
DirExistsWarning=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
ExtraDiskSpaceRequired=450000000
OutputDir=..
OutputBaseFilename=SOUNDsetup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern dark
WizardImageFile=wizard.bmp,wizard@2x.bmp
WizardSmallImageFile=small.bmp,small@2x.bmp
ShowLanguageDialog=auto
SetupLogging=yes
CloseApplications=no
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Messages]
tr.WelcomeLabel2=Bu sihirbaz SOUND müzik uygulamasını bilgisayarına kuracak.%n%nGerekirse Python ve Git de otomatik kurulur; uygulama ve paketleri internetten indirilir (yaklaşık 300 MB). İnternet bağlantısı gerekir.%n%nKurulumdan sonra SOUND güncellemeleri kendiliğinden alır.
en.WelcomeLabel2=This wizard will install the SOUND music app on your computer.%n%nPython and Git are installed automatically if needed; the app and its packages are downloaded from the internet (about 300 MB). An internet connection is required.%n%nAfter installation SOUND updates itself automatically.

[CustomMessages]
tr.AutoStart=Windows açılınca SOUND'u başlat
en.AutoStart=Start SOUND when Windows starts
tr.StepStop=Açık olan SOUND kapatılıyor…
en.StepStop=Closing SOUND if it is running…
tr.StepNet=İnternet bağlantısı denetleniyor…
en.StepNet=Checking the internet connection…
tr.StepWebView=Microsoft Edge WebView2 denetleniyor…
en.StepWebView=Checking Microsoft Edge WebView2…
tr.StepPython=Python denetleniyor (gerekirse kuruluyor, birkaç dakika sürebilir)…
en.StepPython=Checking Python (installing it if needed, this can take a few minutes)…
tr.StepGit=Git denetleniyor (gerekirse kuruluyor; izin istenirse Evet de)…
en.StepGit=Checking Git (installing it if needed; answer Yes if asked for permission)…
tr.StepFetch=SOUND indiriliyor…
en.StepFetch=Downloading SOUND…
tr.StepPackages=Gerekli paketler yükleniyor (ilk kurulumda birkaç dakika sürer)…
en.StepPackages=Installing required packages (takes a few minutes the first time)…
tr.StepFailed=Kurulum bu adımda takıldı.
en.StepFailed=Setup got stuck at this step.
tr.LogAt=Ayrıntılı kayıt: %1%n%nTekrar denemek için Yeniden Dene'ye bas.
en.LogAt=Detailed log: %1%n%nPress Retry to try again.
tr.Aborted=Kurulum tamamlanamadı.
en.Aborted=Setup could not be completed.
tr.NoWrite=SOUND kendi klasörüne yazabilmeli (kitaplık ve güncellemeler için). Program Files ya da Windows klasörü seçilemez.%n%nLütfen başka bir klasör seç; örneğin Belgeler, Masaüstü ya da önerilen klasör.
en.NoWrite=SOUND needs to write to its own folder (library and updates). Program Files or the Windows folder cannot be used.%n%nPlease choose another folder, e.g. Documents, Desktop or the suggested folder.
tr.NotEmpty=Seçtiğin klasör boş değil:%n%1%n%nSOUND'u boş bir klasöre kur. Klasörü seçtikten sonra sonuna \SOUND gibi yeni bir ad ekleyebilirsin; klasör kurulumda oluşturulur.
en.NotEmpty=The selected folder is not empty:%n%1%n%nInstall SOUND into an empty folder. You can add a new name such as \SOUND to the end of the path; the folder is created during installation.
tr.Existing=Bu klasörde SOUND zaten kurulu. Kurulum onu güncelleyip onaracak; kitaplığın (şarkılar, favoriler, albümler) korunur.
en.Existing=SOUND is already installed in this folder. Setup will update and repair it; your library (songs, favourites, albums) is kept.
tr.ReadyDownload=İnternetten indirilecekler:%n      SOUND uygulaması (GitHub)%n      Uygulama paketleri (~250 MB)%n      Python 3.13 ve Git (yalnızca bilgisayarda yoksa)
en.ReadyDownload=To be downloaded:%n      SOUND app (GitHub)%n      App packages (~250 MB)%n      Python 3.13 and Git (only if missing)
tr.KeepData=Kitaplığın da silinsin mi?%n%nİndirdiğin şarkılar, favoriler, albümler ve ayarlar silinir. Hayır dersen %1\data klasöründe kalır; SOUND'u yeniden aynı klasöre kurarsan kaldığın yerden devam eder.
en.KeepData=Also delete your library?%n%nDownloaded songs, favourites, albums and settings will be deleted. If you choose No, they stay in %1\data and SOUND picks them up again if reinstalled to the same folder.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "steps.ps1"; Flags: dontcopy

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Comment: "SOUND müzik"
Name: "{userdesktop}\{#AppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Comment: "SOUND müzik"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Tasks: autostart

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\run.vbs"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: postinstall nowait skipifsilent

[Code]
var
  LogFile, MsgFile, StateFile: String;

function IsUnder(const Path, Root: String): Boolean;
begin
  Result := (Root <> '') and (CompareText(Copy(AddBackslash(Path), 1, Length(AddBackslash(Root))), AddBackslash(Root)) = 0);
end;

function IsEmptyDir(const Dir: String): Boolean;
var
  F: TFindRec;
begin
  Result := True;
  if FindFirst(AddBackslash(Dir) + '*', F) then
    try
      repeat
        if (F.Name <> '.') and (F.Name <> '..') then begin
          Result := False;
          Exit;
        end;
      until not FindNext(F);
    finally
      FindClose(F);
    end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then Exit;
  Dir := RemoveBackslashUnlessRoot(WizardDirValue);
  if IsUnder(Dir, ExpandConstant('{commonpf32}')) or IsUnder(Dir, ExpandConstant('{commonpf64}')) or IsUnder(Dir, ExpandConstant('{win}')) then begin
    MsgBox(CustomMessage('NoWrite'), mbError, MB_OK);
    Result := False;
  end else if DirExists(Dir + '\.git') then
    MsgBox(CustomMessage('Existing'), mbInformation, MB_OK)
  else if DirExists(Dir) and not IsEmptyDir(Dir) then begin
    MsgBox(FmtMessage(CustomMessage('NotEmpty'), [Dir]), mbError, MB_OK);
    Result := False;
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then Result := Result + MemoTasksInfo + NewLine + NewLine;
  Result := Result + CustomMessage('ReadyDownload');
end;

{ steps.ps1'in bir adımını çalıştırır; hata olursa açıklamayı gösterip Yeniden Dene / İptal sorar }
function RunStep(const Step, Status: String; Percent: Integer): Boolean;
var
  Code: Integer;
  Raw: AnsiString;
  Msg, Params: String;
begin
  Result := False;
  while True do begin
    WizardForm.StatusLabel.Caption := Status;
    WizardForm.FilenameLabel.Caption := '';
    WizardForm.ProgressGauge.Max := 100;
    WizardForm.ProgressGauge.Position := Percent;
    DeleteFile(MsgFile);
    Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\steps.ps1') + '" -Step ' + Step +
              ' -App "' + RemoveBackslashUnlessRoot(ExpandConstant('{app}')) + '" -State "' + StateFile +
              '" -Msg "' + MsgFile + '" -Log "' + LogFile + '"';
    Log('Adım: ' + Step);
    if Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0) then begin
      Result := True;
      Exit;
    end;
    Msg := '';
    if LoadStringFromFile(MsgFile, Raw) then Msg := Trim(UTF8Decode(Raw));
    if Msg = '' then Msg := CustomMessage('StepFailed') + #13#10#13#10 + Status;
    if SuppressibleMsgBox(Msg + #13#10#13#10 + FmtMessage(CustomMessage('LogAt'), [LogFile]), mbError, MB_RETRYCANCEL, IDCANCEL) <> IDRETRY then
      Exit;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssInstall then Exit;
  LogFile := ExpandConstant('{%TEMP}\SOUNDsetup.log');
  MsgFile := ExpandConstant('{tmp}\step.msg');
  StateFile := ExpandConstant('{tmp}\step.state');
  DeleteFile(LogFile);
  ExtractTemporaryFile('steps.ps1');
  if not (RunStep('stop', CustomMessage('StepStop'), 2) and
          RunStep('net', CustomMessage('StepNet'), 5) and
          RunStep('webview', CustomMessage('StepWebView'), 10) and
          RunStep('python', CustomMessage('StepPython'), 20) and
          RunStep('git', CustomMessage('StepGit'), 40) and
          RunStep('fetch', CustomMessage('StepFetch'), 55) and
          RunStep('packages', CustomMessage('StepPackages'), 70)) then
    RaiseException(CustomMessage('Aborted'));
  WizardForm.ProgressGauge.Position := 100;
end;

{ Kaldırma: SOUND'u kapat, git ile gelen her şeyi sil; kitaplık (data) isteğe bağlı }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  App, Keep, Cmd: String;
  Code: Integer;
begin
  if CurUninstallStep <> usUninstall then Exit;
  App := RemoveBackslashUnlessRoot(ExpandConstant('{app}'));
  Keep := '1';
  if DirExists(App + '\data') then
    if SuppressibleMsgBox(FmtMessage(CustomMessage('KeepData'), [App]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      Keep := '0';
  StringChangeEx(App, '''', '''''', True);
  { git'in salt okunur dosyalarını da silebilmek için PowerShell Remove-Item -Force }
  Cmd := '-NoProfile -ExecutionPolicy Bypass -Command "$app = ''' + App + '''; ' +
         'Get-CimInstance Win32_Process -Filter \"Name=''pythonw.exe'' OR Name=''python.exe''\" | ' +
         'Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($app + ''\'', ''OrdinalIgnoreCase'') } | ' +
         'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 500; ' +
         'Get-ChildItem -LiteralPath $app -Force | Where-Object { $_.Name -notlike ''unins*'' -and (' + Keep + ' -eq 0 -or $_.Name -ne ''data'') } | ' +
         'Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"';
  Exec('powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;
