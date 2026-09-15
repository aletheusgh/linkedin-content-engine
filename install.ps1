$ErrorActionPreference = "Stop"

$Source = $PSScriptRoot
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillsDir = Join-Path $CodexHome "skills"
$Destination = Join-Path $SkillsDir "linkedin-content-engine"

New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null

$sourceResolved = (Resolve-Path $Source).Path.TrimEnd('\\')
$destExists = Test-Path $Destination
$destResolved = if ($destExists) { (Resolve-Path $Destination).Path.TrimEnd('\\') } else { $null }

if ($destResolved -and $sourceResolved -eq $destResolved) {
    Write-Host "LinkedIn Content Engine is already installed at $Destination"
    exit 0
}

if (Test-Path $Destination) {
    $Backup = "$Destination.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Move-Item $Destination $Backup
    Write-Host "Previous version backed up to $Backup"
}

Copy-Item -Recurse -Force $Source $Destination
Write-Host "Installed LinkedIn Content Engine to $Destination"
Write-Host "Restart Codex before using the skill."
