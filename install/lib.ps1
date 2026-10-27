# Shared helpers for install.ps1 and uninstall.ps1.
# Windows PowerShell 5.1 compatible (no ternary, no ??, no &&). Keep this file ASCII-only:
# PowerShell 5.1 reads BOM-less scripts in the system code page.

$Script:Root = Split-Path -Parent $PSScriptRoot
$Script:AppName = "Kevin's Super Cert Prep 3000"
$Script:MinPython = [version]'3.12'
# Settings written by the old Docker / local-model installer; removed from .env on install.
$Script:ObsoleteEnvKeys = @('CCST_PROVIDER', 'OLLAMA_URL', 'OLLAMA_MODEL', 'OLLAMA_NUM_CTX', 'OLLAMA_TIMEOUT_S',
                            'CCST_BATCH_SIZE', 'CCST_GENERATE_COOLDOWN_S', 'COMPOSE_FILE')

function Write-Step([string]$msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Note([string]$msg) { Write-Host "    ..  $msg" }
function Write-Warn2([string]$msg) { Write-Host "    !!  $msg" -ForegroundColor Yellow }

function Fail([string]$msg) { throw $msg }

# Run a native command; throw with its output if it fails. Returns stdout lines.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments, [switch]$Quiet, [switch]$AllowFail)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } catch {
        $out = @("$_"); $code = 1
    } finally {
        $ErrorActionPreference = $old
    }
    if (-not $Quiet) { $out | ForEach-Object { Write-Host "       $_" } }
    if ($code -ne 0 -and -not $AllowFail) {
        Fail ("'$Exe $($Arguments -join ' ')' failed (exit $code):`n" + ($out | Select-Object -Last 15 | Out-String))
    }
    return ,@($out)
}

# True if a "major.minor[.patch]" version string is at least the minimum the app supports.
function Test-PythonVersion([string]$text) {
    $v = $null
    if (-not [version]::TryParse(($text.Trim() -replace '[^0-9.].*$', ''), [ref]$v)) { return $false }
    return ($v -ge $Script:MinPython)
}

# Ask a Python interpreter for its version and real executable path; $null if it doesn't run.
# (The Microsoft Store "python" placeholder prints nothing and fails, so it's skipped.)
function Get-PythonInfo([string]$exe, [string[]]$prefix) {
    # Single quotes only: Windows PowerShell 5.1 doesn't escape double quotes in native arguments.
    $probe = 'import sys; print(''%d.%d.%d'' % sys.version_info[:3]); print(sys.executable)'
    $out = Invoke-Native $exe ($prefix + @('-c', $probe)) -Quiet -AllowFail
    $lines = @($out | Where-Object { $_ -match '\S' })
    if ($lines.Count -lt 2 -or $lines[0] -notmatch '^\d+\.\d+\.\d+$') { return $null }
    return @{ Version = $lines[0]; Exe = $lines[1].Trim() }
}

# The newest suitable Python on this PC: the "py" launcher first, then "python" on PATH.
function Find-Python {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += , @('py', @('-3')) }
    if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += , @('python', @()) }
    foreach ($c in $candidates) {
        $info = Get-PythonInfo $c[0] $c[1]
        if ($info -and (Test-PythonVersion $info.Version)) { return $info }
    }
    return $null
}

# True if this app (not some other program) answers on the port. Bypasses any system proxy.
function Test-AppAnswers([int]$port) {
    try {
        $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$port/api/chapters")
        $req.Proxy = $null
        $req.Timeout = 3000
        $resp = $req.GetResponse()
        try {
            $text = (New-Object IO.StreamReader($resp.GetResponseStream())).ReadToEnd()
        } finally {
            $resp.Close()
        }
        return $text.TrimStart().StartsWith('[')
    } catch {
        return $false
    }
}

# This project's running app: the run.ps1 window, the .venv launcher, and the interpreter it starts.
function Get-AppProcesses {
    $root = $Script:Root
    $venv = Join-Path $root '.venv'
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $launchers = @($all | Where-Object { $_.CommandLine -match 'ccst\.launch' -and $_.ExecutablePath -and
                                         $_.ExecutablePath.StartsWith($venv, [StringComparison]::OrdinalIgnoreCase) })
    $ids = @($launchers | ForEach-Object { $_.ProcessId })
    $children = @($all | Where-Object { $ids -contains $_.ParentProcessId -and $_.CommandLine -match 'ccst\.launch' })
    $windows = @($all | Where-Object { $_.Name -eq 'powershell.exe' -and $_.CommandLine -and
                                       $_.CommandLine.IndexOf((Join-Path $root 'run.ps1'), [StringComparison]::OrdinalIgnoreCase) -ge 0 })
    return @($children + $launchers + $windows)
}

function Test-PortListening([int]$port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

# Where the app's shortcuts live: the desktop and the Start menu.
function Get-ShortcutPaths {
    $name = "$Script:AppName.lnk"
    return @(
        (Join-Path ([Environment]::GetFolderPath('Desktop')) $name),
        (Join-Path ([Environment]::GetFolderPath('Programs')) $name)
    )
}

# Create (or refresh) a shortcut that starts the app with run.ps1.
function New-AppShortcut([string]$path, [string]$root) {
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $ps
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $root 'run.ps1')`" -PauseOnError"
    $lnk.WorkingDirectory = $root
    $lnk.Description = "Start $Script:AppName and open it in the browser"
    $lnk.Save()
}

# Read and write simple KEY=VALUE pairs in the project .env, keeping other lines intact.
function Get-EnvValue([string]$key) {
    $path = Join-Path $Script:Root '.env'
    if (-not (Test-Path $path)) { return $null }
    foreach ($line in Get-Content $path) {
        if ($line -match "^\s*$([regex]::Escape($key))\s*=(.*)$") { return $Matches[1].Trim() }
    }
    return $null
}

function Set-EnvValue([string]$key, [string]$value) {
    $path = Join-Path $Script:Root '.env'
    $lines = @()
    if (Test-Path $path) { $lines = @(Get-Content $path) }
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($key))\s*=") { $lines[$i] = "$key=$value"; $found = $true }
    }
    if (-not $found) { $lines += "$key=$value" }
    [IO.File]::WriteAllLines($path, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
}

# Remove keys from .env; returns the keys that were present.
function Remove-EnvValue([string[]]$keys) {
    $path = Join-Path $Script:Root '.env'
    if (-not (Test-Path $path)) { return @() }
    $removed = @()
    $kept = @()
    foreach ($line in Get-Content $path) {
        $hit = $keys | Where-Object { $line -match "^\s*$([regex]::Escape($_))\s*=" } | Select-Object -First 1
        if ($hit) { $removed += $hit } else { $kept += $line }
    }
    if ($removed.Count) { [IO.File]::WriteAllLines($path, [string[]]$kept, (New-Object Text.UTF8Encoding($false))) }
    return $removed
}
