; Inno Setup script for the Windows installer (ChessGuru-Setup.exe).
; CI builds the app with PyInstaller first, then runs:
;   iscc /DAppVersion=0.1.0 packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1E7B0A-3F4D-4E8B-9C2A-5D7F1A2B3C4D}
AppName=ChessGuru
AppVersion={#AppVersion}
AppPublisher=ChessGuru
DefaultDirName={localappdata}\Programs\ChessGuru
DefaultGroupName=ChessGuru
; Installs for the current user only, so no admin rights are needed.
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=ChessGuru-Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\ChessGuru.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\ChessGuru\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ChessGuru"; Filename: "{app}\ChessGuru.exe"
Name: "{group}\Uninstall ChessGuru"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ChessGuru"; Filename: "{app}\ChessGuru.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ChessGuru.exe"; Description: "Open ChessGuru now"; Flags: nowait postinstall skipifsilent
