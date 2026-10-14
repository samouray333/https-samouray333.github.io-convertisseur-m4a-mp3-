; Script Inno Setup de PodCast Studio
; Compilation : ISCC.exe /DAppVersion=1.0.0 packaging\installer.iss  (après PyInstaller)
; Fichier enregistré en UTF-8 avec BOM (accents).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "PodCast Studio"
#define AppExe "PodCastStudio.exe"
#define AppPublisher "PodCast"
#ifndef AppRoot
  ; Dossier podcast-studio (parent du dossier de ce script)
  #define AppRoot AddBackslash(SourcePath) + ".."
#endif

[Setup]
AppId={{4B8D2E6A-71C3-4F95-A0D8-3E6B9C1F7A24}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments=Créez vos podcasts à plusieurs voix : script, jingles, épisodes MP3 et flux RSS.
DefaultDirName={autopf}\PodCast Studio
DefaultGroupName=PodCast Studio
DisableProgramGroupPage=yes
OutputDir={#AppRoot}\dist
OutputBaseFilename=PodCastStudio-Setup-{#AppVersion}
SetupIconFile={#AppRoot}\podcaststudio\resources\app.ico
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
fr.AssocProject=Associer les fichiers de projet .pcsproj à PodCast Studio
en.AssocProject=Associate .pcsproj project files with PodCast Studio
fr.LaunchApp=Lancer PodCast Studio
en.LaunchApp=Launch PodCast Studio
fr.ProjectFile=Projet PodCast Studio
en.ProjectFile=PodCast Studio project

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "{cm:AssocProject}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#AppRoot}\dist\PodCastStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PodCast Studio"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\PodCast Studio"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.pcsproj"; ValueType: string; ValueName: ""; ValueData: "PodCastStudio.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PodCastStudio.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:ProjectFile}"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PodCastStudio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PodCastStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
