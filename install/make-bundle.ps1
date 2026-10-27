<#
.SYNOPSIS
  Builds an offline install bundle from this (working) installation.

.DESCRIPTION
  Output folder layout:
    bundle.json            what is inside, with SHA-256 checksums
    images.tar             docker save of the app and Ollama images
    models-<name>.tar      the model files, ready to unpack into the model volume
    ccst\                  the project (app code, objectives, question pool, installer); no progress data
    install-offline.cmd    double-click on the target machine
  Copy the whole folder to the target PC (USB drive, network share) and run install-offline.cmd.
  The target still needs Docker Desktop installed and running (it can't be bundled).

.PARAMETER Out
  Folder to create. It must not exist yet or must be empty.
.PARAMETER Model
  Model to include (default: the installed one from .env, else qwen3:4b).
#>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Out, [string]$Model)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')
Set-Location $Script:Root
$exitCode = 0

try {
    if (-not $Model) { $Model = Get-EnvValue 'OLLAMA_MODEL' }
    if (-not $Model) { $Model = 'qwen3:4b' }
    $name, $tag = $Model.Split(':'); if (-not $tag) { $tag = 'latest' }

    Write-Step 'Checking the source installation'
    if (-not (Test-DockerEngine)) { Fail 'Docker is not running.' }
    foreach ($img in @($Script:AppImage, $Script:OllamaImage)) {
        if (-not (Test-ImagePresent $img)) { Fail "Image $img is missing. Run install\install.ps1 on this machine first." }
    }
    if (-not (Test-VolumePresent $Script:ModelVolume)) { Fail 'The model volume is missing. Run install\install.ps1 first.' }
    $manifestRel = "models/manifests/registry.ollama.ai/library/$name/$tag"
    $json = (Invoke-Native docker @('run', '--rm', '-v', "$($Script:ModelVolume):/root/.ollama:ro", '--entrypoint', 'cat',
        $Script:OllamaImage, "/root/.ollama/$manifestRel") -Quiet -AllowFail) -join "`n"
    try { $manifest = $json | ConvertFrom-Json } catch { Fail "Model $Model is not installed in the volume." }
    $digests = @($manifest.config.digest) + @($manifest.layers | ForEach-Object { $_.digest })
    $files = @($manifestRel) + @($digests | ForEach-Object { 'models/blobs/' + ($_ -replace ':', '-') })
    Write-Ok "Images present; model $Model has $($files.Count) files"

    if (Test-Path $Out) {
        if (Get-ChildItem $Out -Force | Select-Object -First 1) { Fail "$Out already exists and is not empty." }
    } else {
        New-Item -ItemType Directory -Path $Out | Out-Null
    }
    $Out = (Resolve-Path $Out).Path

    Write-Step 'Saving images (several GB; a few minutes)'
    $imagesTar = Join-Path $Out 'images.tar'
    Invoke-Native docker @('save', '-o', $imagesTar, $Script:AppImage, $Script:OllamaImage) -Quiet | Out-Null
    Write-Ok ("images.tar: {0:N2} GB" -f ((Get-Item $imagesTar).Length / 1GB))

    Write-Step "Exporting model $Model"
    $modelFile = "models-$name-$tag.tar" -replace '[^A-Za-z0-9._-]', '_'
    $list = ($files | ForEach-Object { "'$_'" }) -join ' '
    Invoke-Native docker @('run', '--rm', '-v', "$($Script:ModelVolume):/root/.ollama:ro", '-v', "$($Out):/out",
        '--entrypoint', 'sh', $Script:OllamaImage, '-c', "tar -C /root/.ollama -cf '/out/$modelFile' $list") -Quiet | Out-Null
    Write-Ok ("{0}: {1:N2} GB" -f $modelFile, ((Get-Item (Join-Path $Out $modelFile)).Length / 1GB))

    Write-Step 'Copying the project (no progress data, no secrets)'
    $proj = Join-Path $Out 'ccst'
    $items = @('src', 'install', 'Objective Documents', 'Project Documents', 'docker-compose.yml', 'docker-compose.gpu.yml',
               'Dockerfile', '.dockerignore', 'requirements.txt', 'requirements-dev.txt', '.env.example', '.gitignore',
               'CLAUDE.md', 'run.ps1', 'pyproject.toml')
    New-Item -ItemType Directory -Path $proj | Out-Null
    foreach ($i in $items) {
        $src = Join-Path $Script:Root $i
        if (Test-Path $src) { Copy-Item -Path $src -Destination $proj -Recurse }
    }
    foreach ($d in @('data\questions', 'data\authored')) {
        $src = Join-Path $Script:Root $d
        if (Test-Path $src) {
            $dst = Join-Path $proj $d
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Copy-Item -Path (Join-Path $src '*.json') -Destination $dst
        }
    }
    Get-ChildItem $proj -Recurse -Force -Directory -Filter '__pycache__' | ForEach-Object { [IO.Directory]::Delete($_.FullName, $true) }
    Get-ChildItem $proj -Recurse -Force -File -Filter 'install.log' | ForEach-Object { [IO.File]::Delete($_.FullName) }
    Write-Ok 'Project copied to ccst\'

    Write-Step 'Checksums and manifest'
    $info = [ordered]@{
        format = 1
        created = (Get-Date).ToString('yyyy-MM-dd HH:mm')
        model = $Model
        images = @($Script:AppImage, $Script:OllamaImage)
        images_file = 'images.tar'
        images_sha256 = (Get-FileHash $imagesTar -Algorithm SHA256).Hash
        model_file = $modelFile
        model_sha256 = (Get-FileHash (Join-Path $Out $modelFile) -Algorithm SHA256).Hash
    }
    [IO.File]::WriteAllText((Join-Path $Out 'bundle.json'), ($info | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    $cmd = "@echo off`r`nrem Offline install: needs Docker Desktop installed and running on this PC.`r`n" +
           "powershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0ccst\install\install.ps1`" -Bundle `"%~dp0.`" %*`r`necho.`r`npause`r`n"
    [IO.File]::WriteAllText((Join-Path $Out 'install-offline.cmd'), $cmd, (New-Object Text.ASCIIEncoding))
    $total = (Get-ChildItem $Out -Recurse -File | Measure-Object Length -Sum).Sum / 1GB
    Write-Host ''
    Write-Host ("Bundle ready: $Out ({0:N2} GB). Copy the whole folder to the target PC and run install-offline.cmd." -f $total) -ForegroundColor Green
} catch {
    Write-Host ''
    Write-Host "BUNDLE FAILED: $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
}
exit $exitCode
