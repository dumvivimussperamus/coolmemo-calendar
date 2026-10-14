; 메모 일정함 설치파일 (Inno Setup 6)
#define AppName "메모 일정함"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppIdGuid
  #define AppIdGuid "{{6B0E8D52-4B7C-4C0E-9F3A-C0010E5A2025}"
#endif
#define AppExe "MemoCalendar.exe"

[Setup]
AppId={#AppIdGuid}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=CoolMemo Calendar
DefaultDirName={autopf}\CoolMemoCalendar
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=MemoCalendar-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
CloseApplicationsFilter={#AppExe}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 작업:"
Name: "startup"; Description: "Windows 시작 시 자동 실행 (백그라운드)"; GroupDescription: "추가 작업:"; Flags: unchecked

[Files]
Source: "..\dist\app\MemoCalendar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--background"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "메모 일정함 지금 실행"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
    Exec('taskkill.exe', '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\CoolMemoCalendar');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox('설정, Google 연결 정보, 등록 이력도 함께 삭제할까요?' + #13#10 + '(쿨메신저 UDB 파일은 삭제되지 않습니다.)',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
