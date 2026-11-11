; Installateur Windows de Transferys (NSIS, interface moderne en français)
; Compilation : makensis /DVERSION=1.0.0 /DSRC=<dossier Release> installer\transferys.nsi

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!ifndef SRC
  !define SRC "..\..\build\windows\x64\runner\Release"
!endif
!ifndef OUTFILE
  !define OUTFILE "Transferys-Setup-${VERSION}.exe"
!endif

!define APPNAME "Transferys"
!define COMPANY "QMTech"
!define EXE "Transferys.exe"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transferys"

Name "${APPNAME}"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES64\${APPNAME}"
InstallDirRegKey HKLM "Software\${COMPANY}\${APPNAME}" "InstallDir"
; Droits administrateur : nécessaires pour autoriser Transferys dans le
; pare-feu Windows (sinon le téléphone ne peut pas joindre le PC).
RequestExecutionLevel admin
SetCompressor /SOLID lzma
BrandingText "${COMPANY} • ${APPNAME} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1036 "ProductName" "${APPNAME}"
VIAddVersionKey /LANG=1036 "CompanyName" "${COMPANY}"
VIAddVersionKey /LANG=1036 "FileDescription" "Installation de ${APPNAME}"
VIAddVersionKey /LANG=1036 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1036 "LegalCopyright" "(C) 2026 ${COMPANY}"

!define MUI_ICON "..\runner\resources\app_icon.ico"
!define MUI_UNICON "..\runner\resources\app_icon.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Bienvenue dans l'installation de ${APPNAME}"
!define MUI_WELCOMEPAGE_TEXT "Transferys envoie vos fichiers entre ce PC et votre téléphone Android, sans câble, sur votre Wi-Fi.$\r$\n$\r$\nL'installation ajoute aussi :$\r$\n• l'autorisation dans le pare-feu Windows (réseaux privés) ;$\r$\n• « Envoyer avec Transferys » dans le clic droit ;$\r$\n• Transferys dans « Envoyer vers ».$\r$\n$\r$\nCliquez sur Suivant pour continuer."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Transferys"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

!include "x64.nsh"

Function .onInit
  ; Application 64 bits : registre et Program Files en vue 64 bits.
  SetRegView 64
FunctionEnd

Function un.onInit
  SetRegView 64
FunctionEnd

Section "Transferys" SecMain
  SectionIn RO
  ; Ferme une instance en cours (mise à jour)
  nsExec::Exec 'taskkill /F /IM ${EXE}'
  Sleep 500

  SetOutPath "$INSTDIR"
  File /r "${SRC}\*.*"

  ; Raccourcis
  SetShellVarContext current
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\Désinstaller ${APPNAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
  ; « Envoyer vers » : sélection multiple en un seul envoi
  CreateShortCut "$SENDTO\${APPNAME}.lnk" "$INSTDIR\${EXE}" "--send" "$INSTDIR\${EXE}" 0

  ; Clic droit « Envoyer avec Transferys » (fichiers et dossiers)
  WriteRegStr HKCU "Software\Classes\*\shell\Transferys" "MUIVerb" "Envoyer avec Transferys"
  WriteRegStr HKCU "Software\Classes\*\shell\Transferys" "Icon" '"$INSTDIR\${EXE}",0'
  WriteRegStr HKCU "Software\Classes\*\shell\Transferys" "MultiSelectModel" "Player"
  WriteRegStr HKCU "Software\Classes\*\shell\Transferys\command" "" '"$INSTDIR\${EXE}" --send "%1"'
  WriteRegStr HKCU "Software\Classes\Directory\shell\Transferys" "MUIVerb" "Envoyer avec Transferys"
  WriteRegStr HKCU "Software\Classes\Directory\shell\Transferys" "Icon" '"$INSTDIR\${EXE}",0'
  WriteRegStr HKCU "Software\Classes\Directory\shell\Transferys\command" "" '"$INSTDIR\${EXE}" --send "%1"'

  ; Pare-feu Windows : réseaux privés et domaine (jamais « public »)
  nsExec::Exec 'netsh advfirewall firewall delete rule name="Transferys"'
  nsExec::Exec 'netsh advfirewall firewall delete rule name="Transferys (découverte)"'
  nsExec::Exec 'netsh advfirewall firewall add rule name="Transferys" dir=in action=allow program="$INSTDIR\${EXE}" enable=yes profile=private,domain'
  nsExec::Exec 'netsh advfirewall firewall add rule name="Transferys (découverte)" dir=in action=allow protocol=UDP localport=53517 enable=yes profile=private,domain'

  ; Désinstallation propre via « Applications et fonctionnalités »
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\${COMPANY}\${APPNAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINSTKEY}" "Publisher" "${COMPANY}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\${EXE}"
  WriteRegStr HKLM "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${UNINSTKEY}" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /F /IM ${EXE}'
  Sleep 500
  nsExec::Exec 'netsh advfirewall firewall delete rule name="Transferys"'
  nsExec::Exec 'netsh advfirewall firewall delete rule name="Transferys (découverte)"'
  DeleteRegKey HKCU "Software\Classes\*\shell\Transferys"
  DeleteRegKey HKCU "Software\Classes\Directory\shell\Transferys"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Transferys"
  SetShellVarContext current
  Delete "$SENDTO\${APPNAME}.lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${UNINSTKEY}"
  DeleteRegKey HKLM "Software\${COMPANY}\${APPNAME}"
  ; Les fichiers reçus (Téléchargements\Transferys) et les réglages sont conservés.
SectionEnd
