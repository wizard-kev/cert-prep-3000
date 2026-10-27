<#
.SYNOPSIS
  Installs (or repairs) the CCST Cybersecurity prep app on this Windows machine.

.DESCRIPTION
  Safe to run again at any time: every step checks what is already done and skips it.
    1. Checks prerequisites (Docker Desktop running, Compose, disk space, port).
    2. Detects GPU and memory and picks a local model (plan section 13).
    3. Gets the images: from an offline bundle, or pulls/builds them.
    4. Gets the model: from the bundle, from this PC's own Ollama, or downloads it (with progress).
    5. Starts the stack, waits until the app and model are ready, and opens the browser.
  No API key is ever requested or stored; the app runs in local-only (Ollama) mode (SR4).

.PARAMETER Bundle
  Folder created by make-bundle.ps1. Installs without internet access.
.PARAMETER Model
  Override the automatic model choice, e.g. qwen3:8b.
.PARAMETER Port
  Local port for the app (default 8000). Always bound to 127.0.0.1 only.
.PARAMETER StopNativeOllama
  Stop the Windows Ollama app if it is running, without asking.
.PARAMETER NonInteractive
  Never prompt; use defaults.
.PARAMETER NoBrowser
  Don't open the browser at the end.

.EXAMPLE
  install\install.cmd
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\install.ps1 -Bundle D:\ccst-bundle
#>
[CmdletBinding()]
param(
    [string]$Bundle,
    [string]$Model,
    [ValidateRange(1024, 65535)][int]$Port = 0,
    [switch]$StopNativeOllama,
    [switch]$NonInteractive,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')
Set-Location $Script:Root
$log = Join-Path $PSScriptRoot 'install.log'
try { Start-Transcript -Path $log -Append | Out-Null } catch { }
$interactive = (-not $NonInteractive) -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected

function Ask([string]$question, [bool]$default) {
    if (-not $interactive) { return $default }
    $hint = 'y/N'; if ($default) { $hint = 'Y/n' }
    $a = Read-Host "    ??  $question [$hint]"
    if ([string]::IsNullOrWhiteSpace($a)) { return $default }
    return $a.Trim().ToLower().StartsWith('y')
}

function Get-Hardware {
    $hw = [ordered]@{ Gpu = 'none detected'; Nvidia = $false; VramGB = 0.0; RamGB = 0.0; DockerMemGB = 0.0 }
    $hw.RamGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) {
        $line = (& $smi.Source --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1)
        if ($line) {
            $name, $mib = $line.Split(',')
            $hw.Gpu = $name.Trim(); $hw.Nvidia = $true; $hw.VramGB = [math]::Round([double]$mib.Trim() / 1024, 1)
        }
    }
    if (-not $hw.Nvidia) {
        # Dedicated memory per display adapter. Integrated GPUs report a small reserved amount
        # of shared RAM here, which Task Manager also shows as "dedicated".
        $class = 'HKLM:\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
        Get-ChildItem $class -ErrorAction SilentlyContinue | ForEach-Object {
            $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
            if ($p.DriverDesc -and $p.'HardwareInformation.qwMemorySize') {
                $gb = [math]::Round([double]$p.'HardwareInformation.qwMemorySize' / 1GB, 1)
                if ($gb -ge $hw.VramGB) { $hw.Gpu = $p.DriverDesc; $hw.VramGB = $gb }
            }
        }
    }
    $mem = (Invoke-Native docker @('info', '--format', '{{.MemTotal}}') -Quiet -AllowFail)[0]
    if ($mem -match '^\d+$') { $hw.DockerMemGB = [math]::Round([double]$mem / 1GB, 1) }
    return $hw
}

function Test-ModelInVolume([string]$model) {
    $name, $tag = $model.Split(':'); if (-not $tag) { $tag = 'latest' }
    $manifest = "/root/.ollama/models/manifests/registry.ollama.ai/library/$name/$tag"
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & docker run --rm -v "$($Script:ModelVolume):/root/.ollama" --entrypoint sh $Script:OllamaImage -c "test -f '$manifest'" 2>$null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

function Wait-AppReady([int]$port, [int]$timeoutSec) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    $last = ''
    while ((Get-Date) -lt $deadline) {
        try {
            $s = Invoke-RestMethod "http://127.0.0.1:$port/api/status" -TimeoutSec 5
            if ($s.health.reachable -and $s.health.model_present) { return $s }
            $last = "app up; model reachable=$($s.health.reachable) present=$($s.health.model_present)"
        } catch { $last = 'app not answering yet' }
        Start-Sleep 3
    }
    Fail "The app did not become ready within $timeoutSec s ($last). See: docker compose logs"
}

try {
    Write-Host "CCST Cybersecurity prep: installer" -ForegroundColor White
    Write-Note "Project folder: $Script:Root"
    Write-Note "Log: $log"

    # ---- 1. prerequisites ------------------------------------------------
    Write-Step 'Checking prerequisites'
    if ($env:OS -ne 'Windows_NT') { Fail 'This installer is for Windows. (A Linux installer is not built yet.)' }
    if (-not (Test-DockerCli)) {
        Fail ("Docker Desktop is not installed.`n" +
              "  1. In an administrator PowerShell run:  wsl --install --no-distribution   then reboot.`n" +
              "  2. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ (keep 'Use WSL 2').`n" +
              "  3. Start Docker Desktop, wait for 'Engine running', then run this installer again.`n" +
              "  Both steps need administrator rights and usually a reboot, so they can't be automated here.")
    }
    if (-not (Test-DockerEngine)) {
        $dd = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (Test-Path $dd) {
            Write-Note 'Docker Desktop is not running; starting it (this can take a minute or two)...'
            Start-Process $dd
            $deadline = (Get-Date).AddSeconds(240)
            while (-not (Test-DockerEngine) -and (Get-Date) -lt $deadline) { Start-Sleep 5 }
        }
        if (-not (Test-DockerEngine)) { Fail "Docker Desktop is installed but its engine isn't running. Start Docker Desktop, wait for 'Engine running', and run this again." }
    }
    $dv = (Invoke-Native docker @('version', '--format', '{{.Server.Version}}') -Quiet)[0]
    $cv = (Invoke-Native docker @('compose', 'version', '--short') -Quiet -AllowFail)[0]
    if (-not $cv -or $cv -notmatch '^v?2|^v?[3-9]') { Fail 'Docker Compose v2 or later is required (it ships with Docker Desktop).' }
    Write-Ok "Docker $dv, Compose $cv"

    $drive = (Get-Item $env:LOCALAPPDATA).PSDrive
    $freeGB = [math]::Round((Get-PSDrive $drive.Name).Free / 1GB, 1)
    $needGB = 20
    if ($Bundle) { $needGB = [math]::Ceiling(((Get-ChildItem $Bundle -File -Recurse | Measure-Object Length -Sum).Sum / 1GB) * 1.5) + 2 }
    if ($freeGB -lt $needGB) { Fail "Only $freeGB GB free on $($drive.Name): (Docker's storage). About $needGB GB is needed." }
    Write-Ok "$freeGB GB free on $($drive.Name): (need about $needGB GB)"

    # ---- 2. port and native Ollama ----------------------------------------
    if ($Port -eq 0) {
        $Port = 8000
        $saved = Get-EnvValue 'CCST_PORT'
        if ($saved -match '^\d+$') { $Port = [int]$saved }
    }
    # The port may be held by our own running app container; anything else is a conflict.
    $ours = $false
    $appId = (Invoke-Native docker @('ps', '-q', '--filter', "label=com.docker.compose.project=$Script:Project", '--filter', 'label=com.docker.compose.service=app') -Quiet -AllowFail) | Where-Object { $_ } | Select-Object -First 1
    if ($appId) {
        $published = Invoke-Native docker @('port', $appId, '8000') -Quiet -AllowFail
        $ours = [bool]($published | Where-Object { $_ -match ":$Port$" })
    }
    $busy = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($busy -and -not $ours) {
        $owner = (Get-Process -Id ($busy | Select-Object -First 1).OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Fail "Port $Port is already used by '$owner'. Stop it or run again with -Port <another port>, e.g. -Port 8080."
    }
    Write-Ok "Port $Port is available (bound to 127.0.0.1 only)"

    $native = Get-Process -Name 'ollama', 'ollama app' -ErrorAction SilentlyContinue
    if ($native) {
        Write-Warn2 'The Windows Ollama app is running. Running it alongside the Docker stack makes both slow (they share the CPU/GPU).'
        if ($StopNativeOllama -or (Ask 'Stop the Windows Ollama app now? (Reopen it any time from the Start menu.)' $false)) {
            $native | Stop-Process -Force
            Write-Ok 'Stopped the Windows Ollama app'
        } else {
            Write-Note 'Leaving it running. Quit it from the system tray before practicing, or use -StopNativeOllama.'
        }
    }

    # ---- 3. hardware and model ------------------------------------------
    Write-Step 'Detecting hardware'
    $hw = Get-Hardware
    Write-Ok ("GPU: {0} ({1} GB reported); RAM: {2} GB; memory available to Docker: {3} GB" -f $hw.Gpu, $hw.VramGB, $hw.RamGB, $hw.DockerMemGB)
    if (-not $hw.Nvidia -and $hw.VramGB -gt 0 -and $hw.VramGB -lt 4) {
        Write-Note 'This looks like integrated graphics: the reported memory is shared system RAM, not a dedicated card.'
    }

    $bundleInfo = $null
    if ($Bundle) {
        $Bundle = (Resolve-Path $Bundle).Path
        $bundleInfo = Get-Content (Join-Path $Bundle 'bundle.json') -Raw | ConvertFrom-Json
        Write-Ok "Offline bundle: $Bundle (created $($bundleInfo.created), model $($bundleInfo.model))"
    }

    $choice = Select-Model $hw
    $useGpu = $choice.Gpu
    if ($Model) {
        $choice = @{ Model = $Model; Gpu = $useGpu; Why = 'chosen with -Model' }
    } elseif ($bundleInfo) {
        if ($bundleInfo.model -ne $choice.Model) {
            Write-Note "Hardware suggests $($choice.Model), but the bundle contains $($bundleInfo.model); using the bundle's model (no download possible offline)."
        }
        $choice = @{ Model = $bundleInfo.model; Gpu = $useGpu; Why = 'from the offline bundle' }
    } else {
        $prev = Get-EnvValue 'OLLAMA_MODEL'
        if ($prev) { $choice = @{ Model = $prev; Gpu = $useGpu; Why = 'kept from the previous install (use -Model to change)' } }
    }
    if ($bundleInfo -and $choice.Model -ne $bundleInfo.model) { Fail "Model $($choice.Model) is not in the bundle (it has $($bundleInfo.model))." }
    Write-Ok "Model: $($choice.Model) ($($choice.Why)); GPU acceleration: $(if ($useGpu) { 'NVIDIA' } else { 'off (CPU)' })"

    # ---- 4. configuration (.env) ------------------------------------------
    Write-Step 'Writing configuration (.env)'
    if (-not (Get-EnvValue 'CCST_PROVIDER')) { Set-EnvValue 'CCST_PROVIDER' 'ollama' }
    Set-EnvValue 'OLLAMA_MODEL' $choice.Model
    Set-EnvValue 'CCST_PORT' "$Port"
    if ($useGpu) { Set-EnvValue 'COMPOSE_FILE' 'docker-compose.yml;docker-compose.gpu.yml' } else { Remove-EnvValue 'COMPOSE_FILE' }
    New-Item -ItemType Directory -Force (Join-Path $Script:Root 'data\questions') | Out-Null
    Write-Ok 'Local-only mode (Ollama). No API key is stored or needed.'

    # ---- 5. images --------------------------------------------------------
    Write-Step 'Container images'
    if ($bundleInfo) {
        $missing = @($bundleInfo.images | Where-Object { -not (Test-ImagePresent $_) })
        if ($missing.Count) {
            $tar = Join-Path $Bundle $bundleInfo.images_file
            Write-Note "Checking bundle integrity ($([math]::Round((Get-Item $tar).Length / 1GB, 1)) GB)..."
            if ((Get-FileHash $tar -Algorithm SHA256).Hash -ne $bundleInfo.images_sha256) { Fail "Bundle file $tar is corrupt (checksum mismatch). Copy the bundle again." }
            Write-Note 'Loading images from the bundle (a few minutes)...'
            Invoke-Native docker @('load', '-i', $tar) | Out-Null
        }
    } else {
        if (-not (Test-ImagePresent $Script:OllamaImage)) {
            Write-Note "Downloading $Script:OllamaImage (about 3.8 GB). On a slow connection this can take an hour or more."
            & docker pull $Script:OllamaImage
            if ($LASTEXITCODE -ne 0) { Fail "Could not download $Script:OllamaImage. Check the internet connection, or install from an offline bundle with -Bundle." }
        }
        if (-not (Test-ImagePresent $Script:AppImage)) {
            Write-Note 'Building the app image...'
            & docker compose build app
            if ($LASTEXITCODE -ne 0) { Fail 'Building the app image failed (see output above).' }
        }
    }
    foreach ($img in @($Script:OllamaImage, $Script:AppImage)) {
        if (-not (Test-ImagePresent $img)) { Fail "Image $img is still missing." }
    }
    Write-Ok "$Script:AppImage and $Script:OllamaImage present"

    # ---- 6. model ---------------------------------------------------------
    Write-Step "Model $($choice.Model)"
    New-ModelVolume
    if (Test-ModelInVolume $choice.Model) {
        Write-Ok 'Already installed'
    } elseif ($bundleInfo) {
        $mtar = Join-Path $Bundle $bundleInfo.model_file
        if ((Get-FileHash $mtar -Algorithm SHA256).Hash -ne $bundleInfo.model_sha256) { Fail "Bundle file $mtar is corrupt (checksum mismatch)." }
        Write-Note 'Copying the model from the bundle...'
        Invoke-Native docker @('run', '--rm', '-v', "$($Script:ModelVolume):/root/.ollama", '-v', "$($Bundle):/bundle:ro",
            '--entrypoint', 'sh', $Script:OllamaImage, '-c', "tar -C /root/.ollama -xf '/bundle/$($bundleInfo.model_file)'") -Quiet | Out-Null
    } else {
        $store = Get-NativeModelStore
        $files = Get-ModelFiles $store $choice.Model
        if ($files) {
            Write-Note "Found $($choice.Model) in this PC's Ollama ($store); copying it instead of downloading..."
            # No double quotes in the sh script: Windows PowerShell 5.1 does not escape them when
            # passing arguments to native programs. Model paths never contain spaces.
            $dirs = ($files | ForEach-Object { "'/root/.ollama/models/" + ($_ -replace '/[^/]+$', '') + "'" } | Sort-Object -Unique) -join ' '
            $copies = ($files | ForEach-Object { "cp '/src/$_' '/root/.ollama/models/$_'" }) -join '; '
            Invoke-Native docker @('run', '--rm', '-v', "$($Script:ModelVolume):/root/.ollama", '-v', "$($store):/src:ro",
                '--entrypoint', 'sh', $Script:OllamaImage, '-c', "set -e; mkdir -p $dirs; $copies") -Quiet | Out-Null
        } else {
            Write-Note "Downloading $($choice.Model) (progress below). Re-running the installer resumes an interrupted download."
            & docker compose up -d ollama
            if ($LASTEXITCODE -ne 0) { Fail 'Could not start the Ollama container.' }
            $execArgs = @('compose', 'exec')
            if (-not $interactive) { $execArgs += '-T' }
            & docker @execArgs ollama ollama pull $choice.Model
            if ($LASTEXITCODE -ne 0) { Fail "Downloading $($choice.Model) failed. Run the installer again to resume." }
        }
        if (-not (Test-ModelInVolume $choice.Model)) { Fail "Model $($choice.Model) is still missing from the volume." }
        Write-Ok 'Model installed'
    }

    # ---- 7. start ---------------------------------------------------------
    Write-Step 'Starting the app'
    & docker compose up -d --no-build
    if ($LASTEXITCODE -ne 0 -and $useGpu) {
        Write-Warn2 'Starting with the NVIDIA GPU failed (driver or WSL2 GPU support missing?). Falling back to CPU.'
        Remove-EnvValue 'COMPOSE_FILE'
        & docker compose up -d --no-build --force-recreate
    }
    if ($LASTEXITCODE -ne 0) { Fail 'docker compose up failed (see output above).' }
    $status = Wait-AppReady $Port 240
    Write-Ok "App healthy; Ollama reports model $($status.model) available"

    $url = "http://127.0.0.1:$Port/"
    Write-Host ""
    Write-Host "Installed. Open $url" -ForegroundColor Green
    Write-Host "  Start after a reboot:  start Docker Desktop, then run install\install.cmd again (it only starts what's needed)."
    Write-Host "  Stop:                  docker compose stop      (from $Script:Root)"
    Write-Host "  Uninstall:             install\uninstall.cmd"
    if (-not $NoBrowser) { Start-Process $url }
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
