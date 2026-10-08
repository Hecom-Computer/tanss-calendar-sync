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

$versionText = if ($python.Name -eq 'py.exe') { & $python.Source -3 --version } else { & $python.Source --version }
if ($versionText -notmatch 'Python 3\.(1[1-9]|[2-9][0-9])') {
    throw "Python 3.11 oder neuer wird benoetigt (gefunden: $versionText)."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$appDir = Join-Path $InstallRoot 'app'
$configDir = Join-Path $InstallRoot 'config'
$stateDir = Join-Path $InstallRoot 'state'
$logDir = Join-Path $InstallRoot 'log'
$venvDir = Join-Path $appDir '.venv'

foreach ($dir in $appDir, $configDir, $stateDir, $logDir) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

robocopy $repoRoot $appDir /MIR /XD .git .venv __pycache__ /XF *.pem config.json | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Kopieren der Anwendung fehlgeschlagen (robocopy: $LASTEXITCODE)." }

$pythonArgs = if ($python.Name -eq 'py.exe') { @('-3') } else { @() }
& $python.Source @pythonArgs -m venv $venvDir
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install $appDir

$configPath = Join-Path $configDir 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item (Join-Path $appDir 'config.windows.example.json') $configPath
    Write-Warning "Vorlage erstellt: $configPath. Erst 'tanss-sync setup --config `"$configPath`"' ausfuehren."
}

# Nur SYSTEM und Administratoren duerfen Konfiguration, Token, Datenbank und Logs lesen.
& icacls $InstallRoot /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null

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
