; Script Inno Setup de Polyglotte Studio
; Compilation : ISCC.exe /DAppVersion=1.0.0 packaging\installer.iss  (après PyInstaller)
; Fichier enregistré en UTF-8 avec BOM (accents).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Polyglotte Studio"
#define AppExe "PolyglotteStudio.exe"
#define AppPublisher "Polyglotte"
#ifndef AppRoot
  ; Dossier polyglotte-studio (parent du dossier de ce script)
  #define AppRoot AddBackslash(SourcePath) + ".."
#endif

[Setup]
AppId={{4A43C2BC-86B4-438A-9029-8A5C4E70EA38}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments=Apprenez les langues à l'écoute : leçons audio avec voix natives, exercices, révisions espacées.
DefaultDirName={autopf}\Polyglotte Studio
DefaultGroupName=Polyglotte Studio
DisableProgramGroupPage=yes
OutputDir={#AppRoot}\dist
OutputBaseFilename=PolyglotteStudio-Setup-{#AppVersion}
SetupIconFile={#AppRoot}\polyglottestudio\resources\app.ico
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
fr.AssocProject=Associer les fichiers de projet .plgproj à Polyglotte Studio
en.AssocProject=Associate .plgproj project files with Polyglotte Studio
fr.LaunchApp=Lancer Polyglotte Studio
en.LaunchApp=Launch Polyglotte Studio
fr.ProjectFile=Projet Polyglotte Studio
en.ProjectFile=Polyglotte Studio project

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "{cm:AssocProject}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#AppRoot}\dist\PolyglotteStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Polyglotte Studio"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Polyglotte Studio"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.plgproj"; ValueType: string; ValueName: ""; ValueData: "PolyglotteStudio.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PolyglotteStudio.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:ProjectFile}"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PolyglotteStudio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PolyglotteStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
