; Офлайн-установщик «Строительная ERP» (Odoo 19 + PostgreSQL 16 + модули Actually_team)
; Собирается скриптом build.ps1 — вручную не компилировать.
#ifndef AppVersion
  #define AppVersion "1.0"
#endif
#ifndef Stage
  #define Stage "stage"
#endif
#define AppName "Строительная ERP"
#define HttpPort "8069"
#define PgPort "5433"

[Setup]
AppId={{6B1E9C52-2F4C-4C1B-9D1E-5A7E0E6F1C01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Actually_team
DefaultDirName=C:\StroyERP
DisableDirPage=no
DefaultGroupName={#AppName}
OutputDir=output
OutputBaseFilename=StroyERP-Setup-{#AppVersion}
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayName={#AppName}
SetupLogging=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "{#Stage}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Stage}\odoo\*";   DestDir: "{app}\odoo";   Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Stage}\addons\*"; DestDir: "{app}\addons"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Stage}\StroyERP-service.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\stroyerp.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\post_install.ps1";  DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#Stage}\init_company.py";   DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#Stage}\backup.ps1";        DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#Stage}\restore.ps1";       DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#Stage}\uninstall.ps1";     DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#Stage}\update.ps1";        DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#Stage}\verify_update.py";  DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#Stage}\VERSION";           DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\README-клиенту.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "{#Stage}\postgresql-setup.exe"; DestDir: "{app}\setup"; Flags: ignoreversion
Source: "{#Stage}\wkhtmltox-setup.exe";  DestDir: "{app}\setup"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"
Name: "{app}\logs"
Name: "{app}\backups"
Name: "{app}\updates"

[INI]
Filename: "{app}\Строительная ERP.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://127.0.0.1:{#HttpPort}/odoo"

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Строительная ERP.url"; IconFilename: "{app}\stroyerp.ico"
Name: "{group}\{#AppName}"; Filename: "{app}\Строительная ERP.url"; IconFilename: "{app}\stroyerp.ico"
Name: "{group}\Сделать резервную копию"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\backup.ps1"" -Pause"; WorkingDir: "{app}"
Name: "{group}\Восстановить из копии"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\restore.ps1"""; WorkingDir: "{app}"
Name: "{group}\Обновить из файла"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\update.ps1"" -Pick"; WorkingDir: "{app}"
Name: "{group}\Папка с копиями"; Filename: "{app}\backups"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\uninstall.ps1"" -App ""{app}"""; Flags: runhidden waituntilterminated; RunOnceId: "StroyERPUninstall"

[Code]
var
  CompanyPage: TInputQueryWizardPage;

function RandomPassword(Len: Integer): String;
var
  Chars: String;
  I: Integer;
begin
  Chars := 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  Result := '';
  for I := 1 to Len do
    Result := Result + Chars[Random(Length(Chars)) + 1];
end;

function JsonEscape(S: String): String;
begin
  StringChangeEx(S, '\', '\\', True);
  StringChangeEx(S, '"', '\"', True);
  Result := S;
end;

procedure InitializeWizard;
begin
  CompanyPage := CreateInputQueryPage(wpSelectDir,
    'Данные компании', 'Эти данные появятся в договорах и в системе',
    'Пароль нужен для входа в систему (логин: admin). Запишите его.');
  CompanyPage.Add('Название компании:', False);
  CompanyPage.Add('Пароль директора (не короче 6 знаков):', True);
  CompanyPage.Add('Повторите пароль:', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = CompanyPage.ID then
  begin
    if Trim(CompanyPage.Values[0]) = '' then
    begin
      MsgBox('Введите название компании.', mbError, MB_OK);
      Result := False;
    end
    else if Length(CompanyPage.Values[1]) < 6 then
    begin
      MsgBox('Пароль должен быть не короче 6 знаков.', mbError, MB_OK);
      Result := False;
    end
    else if CompanyPage.Values[1] <> CompanyPage.Values[2] then
    begin
      MsgBox('Пароли не совпадают.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ParamsFile, Json: String;
  Lines: TArrayOfString;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    ParamsFile := ExpandConstant('{app}\setup\params.json');
    Json := '{' +
      '"app": "' + JsonEscape(ExpandConstant('{app}')) + '",' +
      '"company": "' + JsonEscape(Trim(CompanyPage.Values[0])) + '",' +
      '"admin_password": "' + JsonEscape(CompanyPage.Values[1]) + '",' +
      '"pg_super_password": "' + RandomPassword(20) + '",' +
      '"db_password": "' + RandomPassword(20) + '",' +
      '"master_password": "' + RandomPassword(20) + '",' +
      '"http_port": {#HttpPort},' +
      '"pg_port": {#PgPort}' +
      '}';
    SetArrayLength(Lines, 1);
    Lines[0] := Json;
    SaveStringsToUTF8File(ParamsFile, Lines, False);
    WizardForm.StatusLabel.Caption := 'Настройка базы данных и системы (5–15 минут)...';
    if not Exec('powershell.exe',
        '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\post_install.ps1') +
        '" -ParamsFile "' + ParamsFile + '"',
        ExpandConstant('{app}'), SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    begin
      DeleteFile(ParamsFile);
      MsgBox('Настройка не завершилась (код ' + IntToStr(ResultCode) + ').' + #13#10 +
             'Журнал: ' + ExpandConstant('{app}\logs\install.log') + #13#10 +
             'Отправьте этот файл разработчику.', mbError, MB_OK);
    end
    else
      DeleteFile(ParamsFile);
  end;
end;
