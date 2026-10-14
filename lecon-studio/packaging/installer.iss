; Script Inno Setup de Leçon Studio
; Compilation : ISCC.exe /DAppVersion=1.0.0 packaging\installer.iss  (après PyInstaller)
; Fichier enregistré en UTF-8 avec BOM (accents).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Leçon Studio"
#define AppExe "LeconStudio.exe"
#define AppPublisher "Lecon"
#ifndef AppRoot
  ; Dossier lecon-studio (parent du dossier de ce script)
  #define AppRoot AddBackslash(SourcePath) + ".."
#endif

[Setup]
AppId={{D72A4C19-3E8B-4B60-9F15-6A0C2E8D4B73}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments=Transformez vos cours Word et PDF en cours audio : leçons, modules, résumés et quiz.
DefaultDirName={autopf}\Leçon Studio
DefaultGroupName=Leçon Studio
DisableProgramGroupPage=yes
OutputDir={#AppRoot}\dist
OutputBaseFilename=LeconStudio-Setup-{#AppVersion}
SetupIconFile={#AppRoot}\leconstudio\resources\app.ico
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
fr.AssocProject=Associer les fichiers de projet .lecproj à Leçon Studio
en.AssocProject=Associate .lecproj project files with Leçon Studio
fr.LaunchApp=Lancer Leçon Studio
en.LaunchApp=Launch Leçon Studio
fr.ProjectFile=Projet Leçon Studio
en.ProjectFile=Leçon Studio project

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "{cm:AssocProject}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#AppRoot}\dist\LeconStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Leçon Studio"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Leçon Studio"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.lecproj"; ValueType: string; ValueName: ""; ValueData: "LeconStudio.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\LeconStudio.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:ProjectFile}"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\LeconStudio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\LeconStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
