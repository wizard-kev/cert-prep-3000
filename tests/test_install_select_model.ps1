# Checks the installer's model choice against plan section 13 using simulated hardware.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File tests\test_install_select_model.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\install\lib.ps1')

$cases = @(
    @{ Name = 'NVIDIA 16 GB';        Hw = @{ Nvidia = $true;  VramGB = 16;  DockerMemGB = 15.5 }; Model = 'qwen3:14b';  Gpu = $true },
    @{ Name = 'NVIDIA 8 GB';         Hw = @{ Nvidia = $true;  VramGB = 8;   DockerMemGB = 7.7 };  Model = 'qwen3:8b';   Gpu = $true },
    @{ Name = 'NVIDIA 4 GB';         Hw = @{ Nvidia = $true;  VramGB = 4;   DockerMemGB = 7.7 };  Model = 'qwen3:4b';   Gpu = $true },
    @{ Name = 'AMD iGPU (this PC)';  Hw = @{ Nvidia = $false; VramGB = 1;   DockerMemGB = 7.2 };  Model = 'qwen3:4b';   Gpu = $false },
    @{ Name = 'Intel iGPU, 32 GB';   Hw = @{ Nvidia = $false; VramGB = 0.1; DockerMemGB = 15.6 }; Model = 'qwen3:4b';   Gpu = $false },
    @{ Name = 'No GPU, small Docker'; Hw = @{ Nvidia = $false; VramGB = 0;   DockerMemGB = 3.8 };  Model = 'qwen3:1.7b'; Gpu = $false }
)
$failed = 0
foreach ($c in $cases) {
    $r = Select-Model $c.Hw
    $ok = ($r.Model -eq $c.Model) -and ($r.Gpu -eq $c.Gpu)
    if (-not $ok) { $failed++ }
    "{0,-5} {1,-22} -> {2} (GPU {3}); expected {4} (GPU {5})" -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $c.Name, $r.Model, $r.Gpu, $c.Model, $c.Gpu
}
exit $failed
