# Shared helpers for install.ps1, uninstall.ps1 and make-bundle.ps1.
# Windows PowerShell 5.1 compatible (no ternary, no ??, no &&).

$Script:Root = Split-Path -Parent $PSScriptRoot
$Script:Project = 'ccst'
$Script:ModelVolume = 'ccst_ollama-models'
$Script:AppImage = 'ccst-app:1.0.0'
$Script:OllamaImage = 'ollama/ollama:0.40.0'

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
    } finally {
        $ErrorActionPreference = $old
    }
    if (-not $Quiet) { $out | ForEach-Object { Write-Host "       $_" } }
    if ($code -ne 0 -and -not $AllowFail) {
        Fail ("'$Exe $($Arguments -join ' ')' failed (exit $code):`n" + ($out | Select-Object -Last 15 | Out-String))
    }
    return ,@($out)
}

function Test-DockerCli { return [bool](Get-Command docker -ErrorAction SilentlyContinue) }

function Test-DockerEngine {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

function Test-ImagePresent([string]$image) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & docker image inspect $image 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

function Test-VolumePresent([string]$name) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & docker volume inspect $name 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

# Create the model volume with Compose labels so Compose adopts it without warnings.
function New-ModelVolume {
    if (Test-VolumePresent $Script:ModelVolume) { return }
    $v = (Invoke-Native docker @('compose', 'version', '--short') -Quiet)[0].Trim()
    Invoke-Native docker @('volume', 'create',
        '--label', "com.docker.compose.project=$Script:Project",
        '--label', 'com.docker.compose.volume=ollama-models',
        '--label', "com.docker.compose.version=$v",
        $Script:ModelVolume) -Quiet | Out-Null
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
    # UTF-8 without BOM: Compose reads the file too.
    [IO.File]::WriteAllLines($path, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
}

function Remove-EnvValue([string]$key) {
    $path = Join-Path $Script:Root '.env'
    if (-not (Test-Path $path)) { return }
    $lines = @(Get-Content $path | Where-Object { $_ -notmatch "^\s*$([regex]::Escape($key))\s*=" })
    [IO.File]::WriteAllLines($path, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
}

# Native Windows Ollama keeps its models here (OLLAMA_MODELS overrides).
function Get-NativeModelStore {
    if ($env:OLLAMA_MODELS) { return $env:OLLAMA_MODELS }
    return (Join-Path $env:USERPROFILE '.ollama\models')
}

# Files (relative to the models dir) that make up one model: its manifest plus every blob it lists.
function Get-ModelFiles([string]$store, [string]$model) {
    $name, $tag = $model.Split(':')
    if (-not $tag) { $tag = 'latest' }
    $rel = "manifests/registry.ollama.ai/library/$name/$tag"
    $manifest = Join-Path $store ($rel -replace '/', '\')
    if (-not (Test-Path $manifest)) { return $null }
    $m = Get-Content $manifest -Raw | ConvertFrom-Json
    $digests = @($m.config.digest) + @($m.layers | ForEach-Object { $_.digest })
    $files = @($rel) + @($digests | ForEach-Object { 'blobs/' + ($_ -replace ':', '-') })
    foreach ($f in $files) {
        if (-not (Test-Path (Join-Path $store ($f -replace '/', '\')))) { return $null }
    }
    return $files
}

# Model choice from detected hardware (plan section 13). Kept here so it can be tested.
function Select-Model($hw) {
    # Plan section 13. Docker Desktop on Windows can use only NVIDIA GPUs (via WSL2); AMD and
    # Intel GPUs fall back to CPU.
    if ($hw.Nvidia) {
        if ($hw.VramGB -ge 15) { return @{ Model = 'qwen3:14b'; Gpu = $true; Why = "NVIDIA GPU with $($hw.VramGB) GB" } }
        if ($hw.VramGB -ge 7.5) { return @{ Model = 'qwen3:8b'; Gpu = $true; Why = "NVIDIA GPU with $($hw.VramGB) GB" } }
        return @{ Model = 'qwen3:4b'; Gpu = $true; Why = "small NVIDIA GPU ($($hw.VramGB) GB)" }
    }
    if ($hw.DockerMemGB -gt 0 -and $hw.DockerMemGB -lt 6) {
        return @{ Model = 'qwen3:1.7b'; Gpu = $false; Why = "no usable GPU and only $($hw.DockerMemGB) GB for Docker" }
    }
    return @{ Model = 'qwen3:4b'; Gpu = $false; Why = 'no NVIDIA GPU; runs on CPU' }
}
