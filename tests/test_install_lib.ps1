# Tests for install\lib.ps1. Run: powershell -ExecutionPolicy Bypass -File tests\test_install_lib.ps1
# Works in a temporary copy of the project root, so the real .env and shortcuts are never touched.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\install\lib.ps1')
$failures = 0
function Check([string]$name, [bool]$ok) {
    if ($ok) { Write-Host "  pass  $name" } else { Write-Host "  FAIL  $name" -ForegroundColor Red; $script:failures++ }
}

# Python version gate (3.12 minimum)
Check 'accepts 3.12.0' (Test-PythonVersion '3.12.0')
Check 'accepts 3.14.8' (Test-PythonVersion '3.14.8')
Check 'accepts 3.13' (Test-PythonVersion '3.13')
Check 'rejects 3.11.9' (-not (Test-PythonVersion '3.11.9'))
Check 'rejects 2.7.18' (-not (Test-PythonVersion '2.7.18'))
Check 'rejects garbage' (-not (Test-PythonVersion 'Python was not found'))
Check 'handles a release tag (3.13.0rc1)' (Test-PythonVersion '3.13.0rc1')

# .env editing, in a scratch root
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("certprep-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $tmp | Out-Null
$realRoot = $Script:Root
$Script:Root = $tmp
try {
    [IO.File]::WriteAllLines((Join-Path $tmp '.env'), [string[]]@('# keep me', 'CCST_PROVIDER=ollama', 'OLLAMA_MODEL=qwen3:4b', 'CCST_PORT=8100'))
    $removed = @(Remove-EnvValue $Script:ObsoleteEnvKeys)
    Check 'removes obsolete model settings' (($removed -join ',') -eq 'CCST_PROVIDER,OLLAMA_MODEL')
    $left = @(Get-Content (Join-Path $tmp '.env'))
    Check 'keeps comments and other settings' (($left -join '|') -eq '# keep me|CCST_PORT=8100')
    Check 'reads a value' ((Get-EnvValue 'CCST_PORT') -eq '8100')
    Set-EnvValue 'CCST_PORT' '8200'
    Check 'updates a value in place' ((Get-EnvValue 'CCST_PORT') -eq '8200' -and @(Get-Content (Join-Path $tmp '.env')).Count -eq 2)
    Check 'second cleanup removes nothing' (@(Remove-EnvValue $Script:ObsoleteEnvKeys).Count -eq 0)

    # CCST_* settings move to their CERTPREP_* names, keeping the value
    $notes = @(Rename-EnvKey $Script:RenamedEnvKeys)
    Check 'renames CCST_PORT' (($notes -join ',') -eq 'CCST_PORT -> CERTPREP_PORT')
    Check 'keeps the port value' ((Get-EnvValue 'CERTPREP_PORT') -eq '8200' -and $null -eq (Get-EnvValue 'CCST_PORT'))
    Set-EnvValue 'CCST_PORT' '9999'
    [void](Rename-EnvKey $Script:RenamedEnvKeys)
    Check 'an existing new key wins' ((Get-EnvValue 'CERTPREP_PORT') -eq '8200' -and $null -eq (Get-EnvValue 'CCST_PORT'))
    Check 'second rename does nothing' (@(Rename-EnvKey $Script:RenamedEnvKeys).Count -eq 0)

    # Shortcut points at run.ps1 in the project root
    $lnkPath = Join-Path $tmp 'test.lnk'
    New-AppShortcut $lnkPath 'C:\Some Folder\App'
    $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($lnkPath)
    Check 'shortcut runs PowerShell' ($lnk.TargetPath -like '*\WindowsPowerShell\v1.0\powershell.exe')
    Check 'shortcut runs run.ps1 with -PauseOnError' ($lnk.Arguments -eq '-NoProfile -ExecutionPolicy Bypass -File "C:\Some Folder\App\run.ps1" -PauseOnError')
    Check 'shortcut starts in the project folder' ($lnk.WorkingDirectory -eq 'C:\Some Folder\App')
} finally {
    $Script:Root = $realRoot
    Remove-Item -LiteralPath $tmp -Recurse -Force
}

# Shortcut locations
$paths = @(Get-ShortcutPaths)
Check 'two shortcut locations' ($paths.Count -eq 2)
Check 'shortcut named after the app' (@($paths | Where-Object { (Split-Path $_ -Leaf) -eq "$Script:AppName.lnk" }).Count -eq 2)

if ($failures) { Write-Host "$failures test(s) failed" -ForegroundColor Red; exit 1 }
Write-Host 'All install library tests passed.' -ForegroundColor Green
exit 0
