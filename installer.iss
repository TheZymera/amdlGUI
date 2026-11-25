[Setup]
AppId={{8F3B9C1A-4D2E-4A7B-9E1C-3F5A7B8C9D0E}
AppName=AMDL
AppVersion=1.2.0
DefaultDirName={localappdata}\AMDL
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_out
OutputBaseFilename=AMDL-Setup
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "release_win\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AMDL"; Filename: "{app}\AMDL.exe"
Name: "{autodesktop}\AMDL"; Filename: "{app}\AMDL.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AMDL.exe"; Description: "{cm:LaunchProgram,AMDL}"; Flags: nowait postinstall skipifsilent

[Code]
function HasNonAscii(const S: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to Length(S) do
  begin
    if Ord(S[I]) > 127 then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and HasNonAscii(WizardDirValue) then
  begin
    MsgBox('Путь установки не должен содержать кириллицу (например, папку «Документы»), иначе встроенный QEMU не сможет запуститься.' + #13#10 + 'Выберите папку с латинским путём, например: C:\Users\konya\AppData\Local\AMDL', mbError, MB_OK);
    Result := False;
  end;
end;