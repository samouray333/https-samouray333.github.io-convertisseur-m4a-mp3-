; Installateur NSIS de Doublys (Echo Matras)
; Compilation (après PyInstaller) : makensis /DAPP_VERSION=1.2.1 packaging\installer.nsi
; Installation pour l'utilisateur courant, sans droits administrateur.

Unicode true
ManifestDPIAware true

!ifndef APP_VERSION
  !define APP_VERSION "1.2.1"
!endif
!ifndef APP_ROOT
  !define APP_ROOT "${__FILEDIR__}\.."
!endif
!define APP_NAME "Doublys"
!define APP_EXE "Doublys.exe"
!define APP_PUBLISHER "Echo Matras"
!define APP_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Doublys"
!define PROG_ID "EchoMatras.Doublys.Project"

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

Name "${APP_NAME}"
Caption "Installation de ${APP_NAME} ${APP_VERSION}"
BrandingText "${APP_PUBLISHER}"
OutFile "${APP_ROOT}\dist\Doublys-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\Doublys"
InstallDirRegKey HKCU "Software\EchoMatras\Doublys" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=1036 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=1036 "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey /LANG=1036 "FileDescription" "Installation de Doublys — doublage vidéo anglais vers français"
VIAddVersionKey /LANG=1036 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1036 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1036 "LegalCopyright" "Echo Matras"

!define MUI_ICON "${APP_ROOT}\doublys\resources\app.ico"
!define MUI_UNICON "${APP_ROOT}\doublys\resources\app.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${APP_ROOT}\packaging\assets\wizard.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${APP_ROOT}\packaging\assets\wizard.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${APP_ROOT}\packaging\assets\header.bmp"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Bienvenue dans l'installation de Doublys"
!define MUI_WELCOMEPAGE_TEXT "Doublys crée la version française de vos vidéos anglaises : séparation des voix, transcription, traduction et voix clonées, sur votre ordinateur.$\r$\n$\r$\nAucun droit administrateur n'est nécessaire. Les moteurs d'IA (environ 6 Go) s'installent au premier lancement, depuis l'application.$\r$\n$\r$\nCliquez sur Suivant pour continuer."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Doublys"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_COMPONENTS
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Doublys nécessite Windows 10 ou 11 en 64 bits."
    Abort
  ${EndIf}
  SetShellVarContext current
FunctionEnd

Function un.onInit
  SetShellVarContext current
FunctionEnd

Section "Doublys (obligatoire)" SecApp
  SectionIn RO
  ; ferme une ancienne version encore ouverte avant de remplacer ses fichiers
  nsExec::Exec 'taskkill /IM "${APP_EXE}" /F'
  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\_internal"
  File /r "${APP_ROOT}\dist\Doublys\*.*"
  WriteUninstaller "$INSTDIR\Desinstaller.exe"

  CreateDirectory "$SMPROGRAMS\Doublys"
  CreateShortcut "$SMPROGRAMS\Doublys\Doublys.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  CreateShortcut "$SMPROGRAMS\Doublys\Désinstaller Doublys.lnk" "$INSTDIR\Desinstaller.exe"

  WriteRegStr HKCU "Software\EchoMatras\Doublys" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${APP_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${APP_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${APP_KEY}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "${APP_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE},0"
  WriteRegStr HKCU "${APP_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APP_KEY}" "UninstallString" '"$INSTDIR\Desinstaller.exe"'
  WriteRegStr HKCU "${APP_KEY}" "QuietUninstallString" '"$INSTDIR\Desinstaller.exe" /S'
  WriteRegStr HKCU "${APP_KEY}" "URLInfoAbout" "https://github.com/samouray333/https-samouray333.github.io-convertisseur-m4a-mp3-/releases"
  WriteRegDWORD HKCU "${APP_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APP_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${APP_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "Raccourci sur le bureau" SecDesktop
  CreateShortcut "$DESKTOP\Doublys.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
SectionEnd

Section "Ouvrir les projets .doublys avec Doublys" SecAssoc
  WriteRegStr HKCU "Software\Classes\.doublys" "" "${PROG_ID}"
  WriteRegStr HKCU "Software\Classes\${PROG_ID}" "" "Projet Doublys"
  WriteRegStr HKCU "Software\Classes\${PROG_ID}\DefaultIcon" "" "$INSTDIR\${APP_EXE},0"
  WriteRegStr HKCU "Software\Classes\${PROG_ID}\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

LangString DESC_App ${LANG_FRENCH} "L'application Doublys et ses outils (FFmpeg, installateur des moteurs)."
LangString DESC_Desktop ${LANG_FRENCH} "Ajoute une icône Doublys sur le bureau."
LangString DESC_Assoc ${LANG_FRENCH} "Double-cliquer sur un projet .doublys l'ouvre dans Doublys."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp} $(DESC_App)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_Desktop)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAssoc} $(DESC_Assoc)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "un.Doublys" UnSecApp
  SectionIn RO
  nsExec::Exec 'taskkill /IM "${APP_EXE}" /F'
  Delete "$DESKTOP\Doublys.lnk"
  RMDir /r "$SMPROGRAMS\Doublys"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\portable.txt"
  Delete "$INSTDIR\Desinstaller.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${APP_KEY}"
  DeleteRegKey HKCU "Software\EchoMatras\Doublys"
  ReadRegStr $0 HKCU "Software\Classes\.doublys" ""
  StrCmp $0 "${PROG_ID}" 0 +2
    DeleteRegKey HKCU "Software\Classes\.doublys"
  DeleteRegKey HKCU "Software\Classes\${PROG_ID}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section /o "un.Supprimer aussi les moteurs d'IA et les réglages (plusieurs Go)" UnSecData
  RMDir /r "$LOCALAPPDATA\Doublys"
  RMDir /r "$APPDATA\Doublys"
SectionEnd

LangString UDESC_App ${LANG_FRENCH} "Supprime l'application. Vos projets (Documents\Doublys) et vos vidéos sont conservés."
LangString UDESC_Data ${LANG_FRENCH} "Supprime aussi les moteurs et modèles téléchargés et les préférences."
!insertmacro MUI_UNFUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${UnSecApp} $(UDESC_App)
  !insertmacro MUI_DESCRIPTION_TEXT ${UnSecData} $(UDESC_Data)
!insertmacro MUI_UNFUNCTION_DESCRIPTION_END
