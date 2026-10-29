; Calorys : installeur Windows (NSIS, installation par utilisateur sans droits admin)
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"

!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!define APPNAME "Calorys"
!define COMPANY "QMTech"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Calorys"
!define WEBVIEW2_GUID "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

Name "${APPNAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "${COMPANY} - ${APPNAME} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1036 "ProductName" "${APPNAME}"
VIAddVersionKey /LANG=1036 "CompanyName" "${COMPANY}"
VIAddVersionKey /LANG=1036 "FileDescription" "Installation de ${APPNAME}"
VIAddVersionKey /LANG=1036 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1036 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1036 "LegalCopyright" "${COMPANY}"

!define MUI_ICON "calorys.ico"
!define MUI_UNICON "calorys.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\Calorys.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Calorys"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

Function .onInit
  ; Calorys s'affiche avec Microsoft Edge WebView2, présent d'origine sur Windows 10 (à jour) et 11.
  ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\${WEBVIEW2_GUID}" "pv"
  ${If} $0 == ""
    ReadRegStr $0 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\${WEBVIEW2_GUID}" "pv"
  ${EndIf}
  ${If} $0 == ""
    ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\${WEBVIEW2_GUID}" "pv"
  ${EndIf}
  ${If} $0 == ""
  ${OrIf} $0 == "0.0.0.0"
    MessageBox MB_YESNO|MB_ICONEXCLAMATION "Calorys a besoin de Microsoft Edge WebView2, qui ne semble pas installé.$\n$\nOuvrir la page de téléchargement officielle (gratuite) ?$\nTu pourras relancer cette installation ensuite." /SD IDNO IDNO +2
      ExecShell "open" "https://developer.microsoft.com/microsoft-edge/webview2/#download-section"
  ${EndIf}
FunctionEnd

Section "Calorys" SecMain
  SetOutPath "$INSTDIR"
  ; Ferme une instance en cours avant de remplacer les fichiers (mise à jour).
  nsExec::Exec 'taskkill /F /IM Calorys.exe'
  File "build\dist\Calorys.exe"
  File "build\dist\resources.neu"
  File "calorys.ico"
  WriteUninstaller "$INSTDIR\Desinstaller.exe"

  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\Calorys.exe" "" "$INSTDIR\calorys.ico"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Désinstaller ${APPNAME}.lnk" "$INSTDIR\Desinstaller.exe"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\Calorys.exe" "" "$INSTDIR\calorys.ico"

  WriteRegStr HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "${COMPANY}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\calorys.ico"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Desinstaller.exe"'
  WriteRegStr HKCU "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\Desinstaller.exe" /S'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" 4500
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /F /IM Calorys.exe'
  Delete "$INSTDIR\Calorys.exe"
  Delete "$INSTDIR\resources.neu"
  Delete "$INSTDIR\calorys.ico"
  Delete "$INSTDIR\Desinstaller.exe"
  RMDir /r "$INSTDIR\.tmp"
  RMDir /r "$INSTDIR\.storage"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\Désinstaller ${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  Delete "$DESKTOP\${APPNAME}.lnk"
  DeleteRegKey HKCU "${UNINSTKEY}"
  DeleteRegKey HKCU "Software\${COMPANY}\${APPNAME}"
  ; Les données (journal) restent dans %APPDATA%\Calorys : une réinstallation les retrouve.
SectionEnd
