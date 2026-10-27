<#
.SYNOPSIS
  Removes Kevin's Super Cert Prep 3000's shortcuts and Python environment from this PC.

.DESCRIPTION
  Safe to run more than once. Stops the app if it is running, removes the desktop and
  Start-menu shortcuts and the .venv folder. Your practice progress (data\progress.db and its
  backups in data\backups) and the certifications with their question pools (data\certs) are kept
  by default, so a later install picks up where you left off.

.PARAMETER RemoveProgress
  Also delete your practice progress: data\progress.db and data\backups (all sessions, answers,
  and progress backups). Asks for confirmation unless -Yes.
.PARAMETER Yes
  Don't ask for confirmation.
#>
[CmdletBinding()]
param([switch]$RemoveProgress, [switch]$Yes)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')
Set-Location $Script:Root
$exitCode = 0

try {
    Write-Host "$($Script:AppName): uninstaller" -ForegroundColor White

    Write-Step 'Stopping the app'
    $venv = Join-Path $Script:Root '.venv'
    $procs = @(Get-AppProcesses)
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    if ($procs.Count) { Write-Ok "Stopped $($procs.Count) app process(es)"; Start-Sleep 1 } else { Write-Ok 'Not running' }

    Write-Step 'Shortcuts'
    foreach ($p in Get-ShortcutPaths) {
        if (Test-Path $p) { Remove-Item -LiteralPath $p -Force; Write-Ok "Removed $p" }
    }

    Write-Step 'Python environment (.venv)'
    if (Test-Path $venv) { Remove-Item -LiteralPath $venv -Recurse -Force; Write-Ok 'Removed' } else { Write-Ok 'Not present' }

    Write-Step 'Your data'
    $progress = @('data\progress.db', 'data\tracker.db', 'data\backups') | ForEach-Object { Join-Path $Script:Root $_ } |
        Where-Object { Test-Path $_ }
    if ($RemoveProgress -and $progress) {
        $go = $Yes
        if (-not $go) {
            $a = Read-Host '    ??  Delete all practice progress (data\progress.db and data\backups)? This cannot be undone. Type DELETE to confirm'
            $go = ($a -ceq 'DELETE')
        }
        if ($go) {
            foreach ($p in $progress) { Remove-Item -LiteralPath $p -Recurse -Force }
            Write-Ok 'Practice progress and its backups deleted'
        } else {
            Write-Ok 'Practice progress kept'
        }
    } else {
        Write-Ok 'Kept: practice progress (data\progress.db, data\backups) and certifications (data\certs)'
    }

    Write-Host ''
    Write-Host 'Uninstalled. To reinstall, run install\install.cmd.' -ForegroundColor Green
    Write-Host 'Python itself was not removed; uninstall it from Windows Settings > Apps if you no longer need it.'
} catch {
    Write-Host ''
    Write-Host "UNINSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
}
exit $exitCode
