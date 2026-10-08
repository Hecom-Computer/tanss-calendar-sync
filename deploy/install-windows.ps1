<#
.SYNOPSIS
Installiert TANSS Calendar Sync auf Windows Server als Task beim Systemstart.

.DESCRIPTION
Der Task laeuft unter LOCAL SYSTEM, startet beim Booten und wird bei Fehlern
automatisch neu gestartet. Die Einrichtung selbst wird bewusst nicht
automatisiert: Sie braucht TANSS- und Microsoft-365-Zugangsdaten.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ProgramData\TANSS Calendar Sync',
    [switch]$Start
)

$ErrorActionPreference = 'Stop'

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($currentIdentity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Bitte PowerShell als Administrator ausfuehren.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) { throw 'Python 3.11 oder neuer ist nicht installiert.' }
$pythonExe = $python.Path
$isLauncher = $python.Name -match '^py(\.exe)?$'

# Der Python Launcher erwartet die Versionswahl vor dem Modul. Eine explizite
# Verzweigung statt leerem Array-Splatting verhindert, dass einzelne Windows-
# Launcher die Optionen verlieren und interaktiv starten.
if ($isLauncher) {
    $versionText = & $pythonExe -3 --version
} else {
    $versionText = & $pythonExe --version
}
if ($versionText -notmatch 'Python 3\.(1[1-9]|[2-9][0-9])') {
    throw "Python 3.11 oder neuer wird benoetigt (gefunden: $versionText)."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
# Der bisherige Ordner ``app`` kann aus einer alten Installation eine gesperrte
# virtuelle Umgebung enthalten. Updates werden deshalb in einem separaten,
# quellcode-only Ordner installiert; die alte Installation bleibt erhalten.
$appDir = Join-Path $InstallRoot 'app-current'
$configDir = Join-Path $InstallRoot 'config'
$stateDir = Join-Path $InstallRoot 'state'
$logDir = Join-Path $InstallRoot 'log'
# Die virtuelle Umgebung liegt bewusst ausserhalb des gespiegelten Quellordners.
# Sonst versucht robocopy beim erneuten Installieren Dateien der laufenden bzw.
# bereits geschuetzten Umgebung zu beruehren.
$venvDir = Join-Path $InstallRoot 'venv'

foreach ($dir in $appDir, $configDir, $stateDir, $logDir) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# Die Laufzeitumgebung liegt ausserhalb von $appDir. /MIR kann daher den
# Quellordner bereinigen, ohne Dateien der laufenden Python-Umgebung anzufassen.
Write-Host 'Kopiere Anwendung ...'
# Ohne /R und /W versucht robocopy bei einem einzelnen gesperrten Element bis zu
# eine Million Mal erneut und wirkt dadurch wie eingefroren.
robocopy $repoRoot $appDir /MIR /R:1 /W:1 /XD .git .venv __pycache__ /XF *.pem config.json | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Kopieren der Anwendung fehlgeschlagen (robocopy: $LASTEXITCODE)." }

if ($isLauncher) {
    & $pythonExe -3 -m venv $venvDir
} else {
    & $pythonExe -m venv $venvDir
}
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install $appDir

$configPath = Join-Path $configDir 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item (Join-Path $appDir 'config.windows.example.json') $configPath
    Write-Warning "Vorlage erstellt: $configPath. Erst 'tanss-sync setup --config `"$configPath`"' ausfuehren."
}

# Nur SYSTEM und lokale Administratoren duerfen Konfiguration, Token, Datenbank und
# Logs lesen. Der alte App-Ordner wird bewusst nicht mehr angefasst, damit eine
# defekte Altinstallation das Update nicht blockiert.
foreach ($dir in $appDir, $configDir, $stateDir, $logDir, $venvDir) {
    & icacls $dir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /T | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Setzen der Zugriffsrechte fehlgeschlagen fuer $dir (icacls: $LASTEXITCODE)."
    }
}

$taskName = 'TANSS Calendar Sync'
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><BootTrigger><Enabled>true</Enabled></BootTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure></Settings>
  <Actions Context="Author"><Exec><Command>$venvPython</Command><Arguments>-m tanss_sync.cli run --config &quot;$configPath&quot;</Arguments><WorkingDirectory>$appDir</WorkingDirectory></Exec></Actions>
</Task>
"@
$xmlPath = Join-Path $env:TEMP 'tanss-calendar-sync-task.xml'
$taskXml | Set-Content -LiteralPath $xmlPath -Encoding Unicode
schtasks.exe /Create /TN $taskName /XML $xmlPath /F | Out-Null
Remove-Item -LiteralPath $xmlPath -Force

Write-Host "Installiert. Konfiguration: $configPath"
Write-Host "Status: schtasks /Query /TN `"$taskName`" /V /FO LIST"
if ($Start) { schtasks.exe /Run /TN $taskName | Out-Null }
