; Script Inno Setup de Conte Studio
; Compilation : ISCC.exe /DAppVersion=1.0.0 packaging\installer.iss  (après PyInstaller)
; Fichier enregistré en UTF-8 avec BOM (accents).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Conte Studio"
#define AppExe "ConteStudio.exe"
#define AppPublisher "Conte"
#ifndef AppRoot
  ; Dossier conte-studio (parent du dossier de ce script)
  #define AppRoot AddBackslash(SourcePath) + ".."
#endif

[Setup]
AppId={{1E43A6F3-6CE6-496E-9057-F3E2770DC557}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments=Créez des contes et histoires audio pour enfants : personnages, bruitages, histoires du soir, livrets.
DefaultDirName={autopf}\Conte Studio
DefaultGroupName=Conte Studio
DisableProgramGroupPage=yes
OutputDir={#AppRoot}\dist
OutputBaseFilename=ConteStudio-Setup-{#AppVersion}
SetupIconFile={#AppRoot}\contestudio\resources\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile={#AppRoot}\packaging\assets\wizard-small-scale.bmp,{#AppRoot}\packaging\assets\wizard.bmp
WizardSmallImageFile={#AppRoot}\packaging\assets\wizard-icon.bmp
; lzma2/ultra (dictionnaire 64 Mo) : ultra64 (1 Go) dépasse la mémoire du compilateur 32 bits
Compression=lzma2/ultra
SolidCompression=yes
LZMAUseSeparateProcess=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes
MinVersion=10.0
ShowLanguageDialog=auto

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.AssocProject=Associer les fichiers de projet .ctsproj à Conte Studio
en.AssocProject=Associate .ctsproj project files with Conte Studio
fr.LaunchApp=Lancer Conte Studio
en.LaunchApp=Launch Conte Studio
fr.ProjectFile=Projet Conte Studio
en.ProjectFile=Conte Studio project

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "{cm:AssocProject}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#AppRoot}\dist\ConteStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Conte Studio"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Conte Studio"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.ctsproj"; ValueType: string; ValueName: ""; ValueData: "ConteStudio.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\ConteStudio.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:ProjectFile}"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\ConteStudio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\ConteStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
