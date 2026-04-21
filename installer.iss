#define MyAppName "ShelfClip"
#define MyAppVersion "1.6.1"
#define MyAppPublisher "Vinicius"
#define MyAppExeName "ShelfClip.exe"
#define SourceDir "C:\Users\vinic\OneDrive\CLAUDE CLI\YOINK WINDOWS\dist"

[Setup]
AppId={{A3F2C8D1-4B7E-4F9A-8C2D-1E5F3A6B9C0D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisherURL=
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=C:\Users\vinic\OneDrive\CLAUDE CLI\YOINK WINDOWS\installer_output
OutputBaseFilename=ShelfClip_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start ShelfClip automatically when Windows starts"; GroupDescription: "Additional options:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch ShelfClip"; Flags: nowait postinstall skipifsilent
