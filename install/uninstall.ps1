<#
.SYNOPSIS
  Removes Kevin's Super Cert Prep 3000's shortcuts and Python environment from this PC.

.DESCRIPTION
  Safe to run more than once. Stops the app if it is running, removes the desktop and
  Start-menu shortcuts and the .venv folder. Your practice progress (data\tracker.db) and the
  question pools are kept by default, so a later install picks up where you left off.

.PARAMETER RemoveProgress
  Also delete data\tracker.db (all sessions and answers). Asks for confirmation unless -Yes.
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
        Write-Ok 'Kept: practice progress (data\tracker.db) and question pools (data\questions)'
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
