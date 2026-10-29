; Installeur de Lisys pour Windows (NSIS 3). Installation pour l'utilisateur, sans droits administrateur.
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"

!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!ifndef SOURCE
  !define SOURCE "..\dist\Lisys"
!endif
!ifndef OUTFILE
  !define OUTFILE "..\dist\Lisys-${VERSION}-installation.exe"
!endif

Name "Lisys"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\Lisys"
InstallDirRegKey HKCU "Software\EchoMatras\Lisys" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "Lisys · Echo Matras"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Lisys"
VIAddVersionKey "CompanyName" "Echo Matras"
VIAddVersionKey "FileDescription" "Installation de Lisys"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Echo Matras"

!define MUI_ICON "..\Lisys\lisys.ico"
!define MUI_UNICON "..\Lisys\lisys.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEFINISHPAGE_BITMAP "welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "welcome.bmp"
!define MUI_WELCOMEPAGE_TITLE "Bienvenue dans l'installation de Lisys"
!define MUI_WELCOMEPAGE_TEXT "Lisys lit à voix haute tes documents (PDF, Word, livres…), les pages web, les photos et tout ce qui est affiché à l'écran.$\r$\n$\r$\nAucun droit administrateur n'est nécessaire.$\r$\n$\r$\nClique sur Suivant pour continuer."
!define MUI_FINISHPAGE_RUN "$INSTDIR\Lisys.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Lisys maintenant"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

!define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\Lisys"

Function .onInit
  ; Lisys a besoin du .NET Framework 4.8 (présent d'office sur Windows 10 à jour et Windows 11).
  ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" "Release"
  ${If} $0 < 528040
    MessageBox MB_YESNO|MB_ICONEXCLAMATION "Lisys a besoin de Microsoft .NET Framework 4.8, qui n'est pas installé sur cet ordinateur.$\r$\n$\r$\nOuvrir la page de téléchargement de Microsoft ?" IDNO +2
      ExecShell "open" "https://dotnet.microsoft.com/download/dotnet-framework/net48"
    Abort
  ${EndIf}
FunctionEnd

Section "Lisys" SecMain
  SectionIn RO
  ; Ferme Lisys s'il tourne déjà (mise à jour).
  nsExec::Exec 'taskkill /IM Lisys.exe /F'
  Sleep 500
  SetOutPath "$INSTDIR"
  File /r "${SOURCE}\*.*"

  CreateShortCut "$SMPROGRAMS\Lisys.lnk" "$INSTDIR\Lisys.exe" "" "$INSTDIR\Lisys.exe" 0 SW_SHOWNORMAL "" "Lecture à voix haute"
  CreateShortCut "$DESKTOP\Lisys.lnk" "$INSTDIR\Lisys.exe" "" "$INSTDIR\Lisys.exe" 0 SW_SHOWNORMAL "" "Lecture à voix haute"

  ; « Lire avec Lisys » dans le menu du clic droit des documents.
  !macro ReadWith EXT
    WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\Lisys" "" "Lire avec Lisys"
    WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\Lisys" "Icon" "$INSTDIR\Lisys.exe"
    WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\Lisys\command" "" '"$INSTDIR\Lisys.exe" "%1"'
  !macroend
  !insertmacro ReadWith ".pdf"
  !insertmacro ReadWith ".docx"
  !insertmacro ReadWith ".odt"
  !insertmacro ReadWith ".epub"
  !insertmacro ReadWith ".rtf"
  !insertmacro ReadWith ".txt"
  !insertmacro ReadWith ".htm"
  !insertmacro ReadWith ".html"
  !insertmacro ReadWith ".jpg"
  !insertmacro ReadWith ".jpeg"
  !insertmacro ReadWith ".png"
  WriteRegStr HKCU "Software\Classes\Applications\Lisys.exe" "FriendlyAppName" "Lisys"
  WriteRegStr HKCU "Software\Classes\Applications\Lisys.exe\shell\open\command" "" '"$INSTDIR\Lisys.exe" "%1"'

  ; Désinstallation propre depuis « Applications et fonctionnalités ».
  WriteUninstaller "$INSTDIR\Desinstaller-Lisys.exe"
  WriteRegStr HKCU "Software\EchoMatras\Lisys" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "Lisys"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST}" "Publisher" "Echo Matras"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\Lisys.exe"
  WriteRegStr HKCU "${UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "UninstallString" '"$INSTDIR\Desinstaller-Lisys.exe"'
  WriteRegStr HKCU "${UNINST}" "QuietUninstallString" '"$INSTDIR\Desinstaller-Lisys.exe" /S'
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINST}" "EstimatedSize" 7500
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /IM Lisys.exe /F'
  Sleep 500
  Delete "$SMPROGRAMS\Lisys.lnk"
  Delete "$DESKTOP\Lisys.lnk"
  RMDir /r "$INSTDIR"
  !macro UnReadWith EXT
    DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\Lisys"
  !macroend
  !insertmacro UnReadWith ".pdf"
  !insertmacro UnReadWith ".docx"
  !insertmacro UnReadWith ".odt"
  !insertmacro UnReadWith ".epub"
  !insertmacro UnReadWith ".rtf"
  !insertmacro UnReadWith ".txt"
  !insertmacro UnReadWith ".htm"
  !insertmacro UnReadWith ".html"
  !insertmacro UnReadWith ".jpg"
  !insertmacro UnReadWith ".jpeg"
  !insertmacro UnReadWith ".png"
  DeleteRegKey HKCU "Software\Classes\Applications\Lisys.exe"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Lisys"
  DeleteRegKey HKCU "${UNINST}"
  DeleteRegKey HKCU "Software\EchoMatras\Lisys"
  ; Les réglages et la bibliothèque (%APPDATA%\Lisys) et les fichiers audio (Documents\Lisys) sont gardés.
SectionEnd
