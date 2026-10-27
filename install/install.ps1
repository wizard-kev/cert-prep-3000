<#
.SYNOPSIS
  Installs (or repairs) Kevin's Super Cert Prep 3000 on this Windows PC.

.DESCRIPTION
  Safe to run again at any time: every step checks what is already done and skips it.
    1. Finds Python 3.12 or newer.
    2. Creates the app's own Python environment (.venv) and installs its pinned packages.
    3. Removes settings left over from the old Docker / local-model setup.
    4. Checks the port and adds desktop and Start-menu shortcuts.
    5. Starts the app and opens it in the browser.
  No AI model, Docker, or API key is needed: questions are written with Claude in a web chat.

.PARAMETER Port
  Local port for the app (default 8000, or the one saved in .env). Always bound to 127.0.0.1 only.
.PARAMETER NoShortcuts
  Don't create the desktop and Start-menu shortcuts.
.PARAMETER NoStart
  Don't start the app at the end.

.EXAMPLE
  install\install.cmd
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\install.ps1 -Port 8080
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 0,
    [switch]$NoShortcuts,
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')
Set-Location $Script:Root
$log = Join-Path $PSScriptRoot 'install.log'
try { Start-Transcript -Path $log -Append | Out-Null } catch { }

try {
    Write-Host "$($Script:AppName): installer" -ForegroundColor White
    Write-Note "Project folder: $Script:Root"
    Write-Note "Log: $log"
    if ($env:OS -ne 'Windows_NT') { Fail 'This installer is for Windows.' }

    # ---- 1. Python ----------------------------------------------------------
    Write-Step "Finding Python $Script:MinPython or newer"
    $python = Find-Python
    if (-not $python) {
        Fail ("Python $Script:MinPython or newer was not found.`n" +
              "  Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'),`n" +
              "  or in PowerShell run:  winget install -e --id Python.Python.3.13`n" +
              "  then run this installer again.")
    }
    Write-Ok "Python $($python.Version) ($($python.Exe))"

    # ---- 2. environment and packages ---------------------------------------
    Write-Step 'Python environment (.venv)'
    $venvPy = Join-Path $Script:Root '.venv\Scripts\python.exe'
    $venvOk = $false
    if (Test-Path $venvPy) {
        $info = Get-PythonInfo $venvPy @()
        $venvOk = [bool]($info -and (Test-PythonVersion $info.Version))
        if ($venvOk) { Write-Ok "Existing environment works (Python $($info.Version))" }
        else { Write-Note 'The existing environment is broken or too old; rebuilding it...' }
    }
    if (-not $venvOk) {
        Invoke-Native $python.Exe @('-m', 'venv', '--clear', (Join-Path $Script:Root '.venv')) -Quiet | Out-Null
        Write-Ok 'Created'
    }
    Write-Note 'Installing packages (requirements.txt)...'
    Invoke-Native $venvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '--quiet', '-r',
                            (Join-Path $Script:Root 'requirements.txt')) -Quiet | Out-Null
    Invoke-Native $venvPy @('-c', 'import fastapi, uvicorn, pydantic') -Quiet | Out-Null
    Write-Ok 'Packages installed'

    # ---- 3. configuration ----------------------------------------------------
    Write-Step 'Configuration (.env)'
    $removed = @(Remove-EnvValue $Script:ObsoleteEnvKeys)
    if ($removed.Count) { Write-Ok "Removed old settings no longer used: $($removed -join ', ')" }
    if ($Port -ne 0) {
        Set-EnvValue 'CCST_PORT' "$Port"
    } else {
        $Port = 8000
        $saved = Get-EnvValue 'CCST_PORT'
        if ($saved -match '^\d+$') { $Port = [int]$saved }
    }
    Write-Ok "Port $Port (bound to 127.0.0.1 only)"
    foreach ($d in @('data', 'data\questions')) { New-Item -ItemType Directory -Force (Join-Path $Script:Root $d) | Out-Null }

    $running = Test-AppAnswers $Port
    if (-not $running -and (Test-PortListening $Port)) {
        $owner = (Get-Process -Id (Get-NetTCPConnection -State Listen -LocalPort $Port | Select-Object -First 1).OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Fail "Port $Port is already used by '$owner'. Close it, or run again with -Port <another port>, e.g. -Port 8080."
    }

    # ---- 4. shortcuts ----------------------------------------------------------
    Write-Step 'Shortcuts'
    if ($NoShortcuts) {
        Write-Ok 'Skipped (-NoShortcuts)'
    } else {
        foreach ($p in Get-ShortcutPaths) {
            New-AppShortcut $p $Script:Root
            Write-Ok $p
        }
    }

    # ---- 5. start ---------------------------------------------------------------
    $url = "http://127.0.0.1:$Port/"
    if ($running) {
        Write-Step 'Starting the app'
        Write-Ok "Already running at $url (restart it to load any updated code)"
    } elseif (-not $NoStart) {
        Write-Step 'Starting the app'
        Start-Process (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$(Join-Path $Script:Root 'run.ps1')`"", '-PauseOnError') `
            -WorkingDirectory $Script:Root
        $deadline = (Get-Date).AddSeconds(60)
        while (-not (Test-AppAnswers $Port) -and (Get-Date) -lt $deadline) { Start-Sleep 1 }
        if (-not (Test-AppAnswers $Port)) { Fail "The app did not start within 60 s. Check the app's window for an error." }
        Write-Ok "Running at $url (the browser opens it)"
    }

    Write-Host ""
    Write-Host "Installed." -ForegroundColor Green
    Write-Host "  Start:      the '$Script:AppName' shortcut on the desktop or in the Start menu (or run.ps1)."
    Write-Host "  Stop:       close the app's window."
    Write-Host "  Uninstall:  install\uninstall.cmd   (keeps your progress unless you add -RemoveProgress)"
    $exitCode = 0
} catch {
    Write-Host ""
    Write-Host "INSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Nothing is half-installed in a harmful way: fix the problem above and run the installer again."
    $exitCode = 1
} finally {
    try { Stop-Transcript | Out-Null } catch { }
}
exit $exitCode
