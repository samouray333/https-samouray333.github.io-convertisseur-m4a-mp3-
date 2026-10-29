/* Calorys (Windows) : rappels même quand l'appli est fermée.
   Les rappels sont confiés au Planificateur de tâches de Windows (tâches « Calorys Rappel N »,
   sans droits administrateur). À l'heure dite, un petit script PowerShell lancé sans fenêtre
   affiche une notification Windows au nom de Calorys ; « Ouvrir Calorys » relance l'appli. */
(function () {
  'use strict';
  const isWin = typeof window.NL_PORT !== 'undefined' && window.NL_OS === 'Windows' && typeof window.Neutralino !== 'undefined';
  const AUMID = 'QMTech.Calorys';
  let dir = null;

  const NOTIFY_PS1 = `param([string]$Id)
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$all = Get-Content -Raw -Encoding UTF8 (Join-Path $dir 'reminders.json') | ConvertFrom-Json
$r = $all.items | Where-Object { [string]$_.id -eq $Id } | Select-Object -First 1
if (-not $r) { exit 0 }
function X([string]$s) { [System.Security.SecurityElement]::Escape($s) }
$icon = Join-Path $dir 'calorys.png'
$xml = @"
<toast launch="calorys://ouvrir" activationType="protocol">
  <visual><binding template="ToastGeneric">
    <text>$(X $r.title)</text><text>$(X $r.text)</text>
    <image placement="appLogoOverride" src="file:///$($icon -replace '\\\\','/')"/>
  </binding></visual>
  <actions><action content="Ouvrir Calorys" activationType="protocol" arguments="calorys://ouvrir"/></actions>
</toast>
"@
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('${AUMID}').Show([Windows.UI.Notifications.ToastNotification]::new($doc))
`;

  // Lanceur sans fenêtre (une console PowerShell clignoterait sinon).
  const NOTIFY_VBS = `Set sh = CreateObject("WScript.Shell")
d = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.Run "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & d & "\\notify.ps1"" -Id " & WScript.Arguments(0), 0, False
`;

  /* Recrée toutes les tâches à partir de reminders.json (heures locales, indépendant de la langue de Windows). */
  const SETUP_PS1 = `$ErrorActionPreference = 'Continue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cfg = Get-Content -Raw -Encoding UTF8 (Join-Path $dir 'reminders.json') | ConvertFrom-Json
# Nom et icône des notifications, lien calorys:// pour rouvrir l'appli.
$k = 'HKCU:\\Software\\Classes\\AppUserModelId\\${AUMID}'
New-Item -Path $k -Force | Out-Null
Set-ItemProperty -Path $k -Name DisplayName -Value 'Calorys'
Set-ItemProperty -Path $k -Name IconUri -Value (Join-Path $dir 'calorys.png')
if ($cfg.exe) {
  $p = 'HKCU:\\Software\\Classes\\calorys'
  New-Item -Path "$p\\shell\\open\\command" -Force | Out-Null
  Set-ItemProperty -Path $p -Name '(default)' -Value 'URL:Calorys'
  Set-ItemProperty -Path $p -Name 'URL Protocol' -Value ''
  Set-ItemProperty -Path "$p\\shell\\open\\command" -Name '(default)' -Value ('"' + $cfg.exe + '"')
}
Get-ScheduledTask -TaskName 'Calorys Rappel *' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
$vbs = Join-Path $dir 'notify.vbs'
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
foreach ($r in $cfg.items) {
  if ($r.once) { $t = New-ScheduledTaskTrigger -Once -At ([DateTime]::Parse($r.once, [Globalization.CultureInfo]::InvariantCulture)) }
  else { $h, $m = $r.at.Split(':'); $t = New-ScheduledTaskTrigger -Daily -At ([DateTime]::Today.AddHours([int]$h).AddMinutes([int]$m)) }
  $a = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('"' + $vbs + '" ' + $r.id)
  Register-ScheduledTask -TaskName ('Calorys Rappel ' + $r.id) -Action $a -Trigger $t -Settings $set -Description 'Rappel Calorys' -Force | Out-Null
}
'OK ' + @($cfg.items).Count
`;

  async function ensureFiles() {
    if (dir) return dir;
    const data = await Neutralino.os.getPath('data');
    dir = data + '\\Calorys';
    try { await Neutralino.filesystem.createDirectory(dir); } catch (e) { /* existe */ }
    // BOM UTF-8 : Windows PowerShell 5.1 lit sinon les accents de travers.
    await Neutralino.filesystem.writeFile(dir + '\\notify.ps1', '﻿' + NOTIFY_PS1);
    await Neutralino.filesystem.writeFile(dir + '\\setup-reminders.ps1', '﻿' + SETUP_PS1);
    await Neutralino.filesystem.writeFile(dir + '\\notify.vbs', NOTIFY_VBS.replace(/\n/g, '\r\n'));
    try {
      const png = await Neutralino.resources.readBinaryFile('/resources/img/icon-192.png');
      await Neutralino.filesystem.writeBinaryFile(dir + '\\calorys.png', png);
    } catch (e) { /* icône facultative */ }
    return dir;
  }

  function localIso(ms) {
    const d = new Date(ms), p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':00';
  }

  /* plan : [{id, at:'HH:MM', title, text}] ; fastEnd : horodatage ms (0 si aucun). */
  async function apply(plan, fastEnd) {
    if (!isWin) return false;
    const d = await ensureFiles();
    const items = plan.map(x => ({ id: x.id, at: x.at, title: x.title, text: x.text }));
    if (fastEnd && fastEnd > Date.now() + 60000) items.push({ id: 99, once: localIso(fastEnd), title: 'Jeûne terminé', text: 'Objectif atteint : tu peux rompre le jeûne. Bravo !' });
    const exe = (window.NL_PATH || '') + '\\Calorys.exe';
    await Neutralino.filesystem.writeFile(d + '\\reminders.json', JSON.stringify({ exe, items }));
    const r = await Neutralino.os.execCommand('powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + d + '\\setup-reminders.ps1"');
    return /OK/.test((r && r.stdOut) || '');
  }

  window.WinReminders = { available: isWin, apply, _scripts: { NOTIFY_PS1, NOTIFY_VBS, SETUP_PS1 } };
})();
