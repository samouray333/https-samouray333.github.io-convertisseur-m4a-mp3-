; Installeur Windows de Telechargys (version native WebView2).
; makensis -DVERSION=1.3.0 -DSRC=<dossier contenant Telechargys.exe et extension\> -DOUT=<fichier.exe> telechargys.nsi

Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

!ifndef VERSION
  !define VERSION "1.3.0"
!endif
!define APPKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\QMTech.Telechargys"

Name "Telechargys"
Caption "Installation de Telechargys ${VERSION}"
OutFile "${OUT}"
InstallDir "$LOCALAPPDATA\QMTech\Telechargys"
InstallDirRegKey HKCU "${APPKEY}" "InstallLocation"
BrandingText "QMTech"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1036 "ProductName" "Telechargys"
VIAddVersionKey /LANG=1036 "CompanyName" "QMTech"
VIAddVersionKey /LANG=1036 "FileDescription" "Installation de Telechargys"
VIAddVersionKey /LANG=1036 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1036 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1036 "LegalCopyright" "© QMTech"

!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\Telechargys.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Telechargys"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

Var Relancer

; Ferme Telechargys s'il tourne (mise à jour) : d'abord on lui laisse le temps de quitter seul.
!macro FermerTelechargys
  Sleep 1500
  nsExec::Exec 'taskkill /IM Telechargys.exe /T /F'
  Pop $0
  Sleep 500
!macroend

; Désinstalle l'ancienne version (Electron), installée ailleurs sous une autre clé.
Function RetirerAncienneVersion
  StrCpy $0 0
  boucle:
    EnumRegKey $1 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall" $0
    StrCmp $1 "" fin
    IntOp $0 $0 + 1
    StrCmp $1 "QMTech.Telechargys" boucle
    ReadRegStr $2 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\$1" "DisplayName"
    StrCmp $2 "Telechargys" 0 boucle
    ReadRegStr $3 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\$1" "QuietUninstallString"
    StrCmp $3 "" boucle
    DetailPrint "Retrait de l'ancienne version de Telechargys…"
    ExecWait '$3'
    Sleep 2000
    StrCpy $0 0
    Goto boucle
  fin:
FunctionEnd

Section "Telechargys" SecMain
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "/RELANCER" $R1
  ${IfNot} ${Errors}
    StrCpy $Relancer "1"
  ${EndIf}

  !insertmacro FermerTelechargys
  Call RetirerAncienneVersion

  SetOutPath "$INSTDIR"
  File "${SRC}\Telechargys.exe"
  File "app.ico"
  SetOutPath "$INSTDIR\extension"
  File /r "${SRC}\extension\*.*"
  SetOutPath "$INSTDIR"

  WriteUninstaller "$INSTDIR\Desinstaller.exe"
  CreateShortCut "$SMPROGRAMS\Telechargys.lnk" "$INSTDIR\Telechargys.exe" "" "$INSTDIR\app.ico"
  ${If} $Relancer != "1"
  ${OrIfNot} ${FileExists} "$DESKTOP\Telechargys.lnk"
    CreateShortCut "$DESKTOP\Telechargys.lnk" "$INSTDIR\Telechargys.exe" "" "$INSTDIR\app.ico"
  ${EndIf}

  WriteRegStr HKCU "${APPKEY}" "DisplayName" "Telechargys"
  WriteRegStr HKCU "${APPKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${APPKEY}" "Publisher" "QMTech"
  WriteRegStr HKCU "${APPKEY}" "DisplayIcon" "$INSTDIR\app.ico"
  WriteRegStr HKCU "${APPKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APPKEY}" "UninstallString" '"$INSTDIR\Desinstaller.exe"'
  WriteRegStr HKCU "${APPKEY}" "QuietUninstallString" '"$INSTDIR\Desinstaller.exe" /S'
  WriteRegDWORD HKCU "${APPKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APPKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "${APPKEY}" "EstimatedSize" $0
SectionEnd

; mise à jour silencieuse lancée par l'appli : on relance Telechargys à la fin
Function .onInstSuccess
  ${If} $Relancer == "1"
    Exec '"$INSTDIR\Telechargys.exe"'
  ${EndIf}
FunctionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /IM Telechargys.exe /T /F'
  Pop $0
  Sleep 500
  Delete "$INSTDIR\Telechargys.exe"
  Delete "$INSTDIR\app.ico"
  Delete "$INSTDIR\Desinstaller.exe"
  RMDir /r "$INSTDIR\extension"
  RMDir "$INSTDIR"
  RMDir "$LOCALAPPDATA\QMTech"
  Delete "$SMPROGRAMS\Telechargys.lnk"
  Delete "$DESKTOP\Telechargys.lnk"
  DeleteRegKey HKCU "${APPKEY}"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Telechargys"
  DeleteRegKey HKCU "Software\Classes\AppUserModelId\QMTech.Telechargys"
  ; la liste des téléchargements et les réglages (%APPDATA%\Telechargys) sont conservés
SectionEnd
