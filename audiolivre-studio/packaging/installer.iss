; Script Inno Setup d'AudioLivre Studio
; Compilation : ISCC.exe /DAppVersion=1.0.0 packaging\installer.iss  (après PyInstaller)
; Fichier enregistré en UTF-8 avec BOM (accents).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "AudioLivre Studio"
#define AppExe "AudioLivreStudio.exe"
#define AppPublisher "AudioLivre"
#ifndef AppRoot
  ; Dossier audiolivre-studio (parent du dossier de ce script)
  #define AppRoot AddBackslash(SourcePath) + ".."
#endif

[Setup]
AppId={{9C3E5B71-6A2D-4E8F-B1C4-5D7A2F9E3B60}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments=Transformez vos documents Word et PDF en livres audio professionnels.
DefaultDirName={autopf}\AudioLivre Studio
DefaultGroupName=AudioLivre Studio
DisableProgramGroupPage=yes
OutputDir={#AppRoot}\dist
OutputBaseFilename=AudioLivreStudio-Setup-{#AppVersion}
SetupIconFile={#AppRoot}\audiolivre\resources\app.ico
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
fr.AssocProject=Associer les fichiers de projet .alsproj à AudioLivre Studio
en.AssocProject=Associate .alsproj project files with AudioLivre Studio
fr.LaunchApp=Lancer AudioLivre Studio
en.LaunchApp=Launch AudioLivre Studio
fr.ProjectFile=Projet AudioLivre Studio
en.ProjectFile=AudioLivre Studio project

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "{cm:AssocProject}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#AppRoot}\dist\AudioLivreStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AudioLivre Studio"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\AudioLivre Studio"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.alsproj"; ValueType: string; ValueName: ""; ValueData: "AudioLivreStudio.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\AudioLivreStudio.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:ProjectFile}"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\AudioLivreStudio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\AudioLivreStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
