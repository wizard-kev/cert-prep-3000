<#
.SYNOPSIS
  Removes the CCST prep app's containers, network, model volume, and images.

.DESCRIPTION
  Safe to run more than once. Your practice progress (data\tracker.db) and the question pool
  are kept by default, so a later install picks up where you left off.

.PARAMETER KeepImages
  Keep the downloaded images (saves a 3.8 GB download if you reinstall).
.PARAMETER KeepModel
  Keep the model volume (saves the model download if you reinstall).
.PARAMETER RemoveProgress
  Also delete data\tracker.db (all sessions and answers). Asks for confirmation unless -Yes.
.PARAMETER Yes
  Don't ask for confirmation.
#>
[CmdletBinding()]
param([switch]$KeepImages, [switch]$KeepModel, [switch]$RemoveProgress, [switch]$Yes)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')
Set-Location $Script:Root
$exitCode = 0

try {
    Write-Host 'CCST Cybersecurity prep: uninstaller' -ForegroundColor White
    if (-not (Test-DockerCli) -or -not (Test-DockerEngine)) {
        Fail 'Docker is not running, so containers and images cannot be removed. Start Docker Desktop and run this again.'
    }

    Write-Step 'Stopping and removing containers and network'
    $downArgs = @('compose', 'down', '--remove-orphans')
    if (-not $KeepModel) { $downArgs += '--volumes' }
    Invoke-Native docker $downArgs | Out-Null
    # 'down' skips services in inactive profiles (ollama-pull); remove anything left with our project label.
    $left = @(Invoke-Native docker @('ps', '-a', '-q', '--filter', "label=com.docker.compose.project=$Script:Project") -Quiet | Where-Object { $_ })
    if ($left.Count) { Invoke-Native docker (@('rm', '-f') + $left) -Quiet | Out-Null }
    # The model volume may exist without containers (e.g. created by the installer before a failure).
    if (-not $KeepModel -and (Test-VolumePresent $Script:ModelVolume)) {
        Invoke-Native docker @('volume', 'rm', $Script:ModelVolume) -Quiet | Out-Null
    }
    if ($KeepModel) { Write-Ok "Containers removed; model volume $Script:ModelVolume kept" } else { Write-Ok 'Containers, network, and model volume removed' }

    Write-Step 'Images'
    if ($KeepImages) {
        Write-Ok 'Kept (use without -KeepImages to remove them)'
    } else {
        foreach ($img in @($Script:AppImage, $Script:OllamaImage)) {
            if (Test-ImagePresent $img) {
                Invoke-Native docker @('image', 'rm', $img) -Quiet | Out-Null
                Write-Ok "Removed $img"
            } else {
                Write-Ok "$img not present"
            }
        }
    }

    Write-Step 'Configuration'
    foreach ($k in @('OLLAMA_MODEL', 'CCST_PORT', 'COMPOSE_FILE')) { Remove-EnvValue $k }
    Write-Ok 'Installer settings removed from .env (other settings kept)'

    Write-Step 'Your data'
    $db = Join-Path $Script:Root 'data\tracker.db'
    if ($RemoveProgress -and (Test-Path $db)) {
        $go = $Yes
        if (-not $go) {
            $a = Read-Host '    ??  Delete all practice progress (data\tracker.db)? This cannot be undone. Type DELETE to confirm'
            $go = ($a -ceq 'DELETE')
        }
        if ($go) {
            [IO.File]::Delete($db)
            Write-Ok 'Practice progress deleted'
        } else {
            Write-Ok 'Practice progress kept'
        }
    } else {
        Write-Ok "Kept: practice progress (data\tracker.db) and question pool (data\questions)"
    }

    Write-Host ''
    Write-Host 'Uninstalled. To reinstall, run install\install.cmd.' -ForegroundColor Green
    Write-Host 'Docker Desktop itself was not removed; uninstall it from Windows Settings > Apps if you no longer need it.'
} catch {
    Write-Host ''
    Write-Host "UNINSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
}
exit $exitCode
