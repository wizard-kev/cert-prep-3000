# Starts the app on http://127.0.0.1:8000 (localhost only; the port can be changed with CERTPREP_PORT in .env)
# and opens it in the browser. Close the window, or press Ctrl+C, to stop it.
# Install first with install\install.cmd, which also adds desktop and Start-menu shortcuts that run this.
param(
    [switch]$NoBrowser,     # start without opening the browser
    [switch]$PauseOnError   # keep the window open after a failure (used by the shortcuts)
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
try { $Host.UI.RawUI.WindowTitle = "Kevin's Super Cert Prep 3000" } catch { }
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$code = 1
if (-not (Test-Path $python)) {
    Write-Host "The app isn't installed yet. Run install\install.cmd first." -ForegroundColor Red
} else {
    $env:PYTHONPATH = Join-Path $PSScriptRoot "src"
    $launchArgs = @("-m", "certprep.launch")
    if ($NoBrowser) { $launchArgs += "--no-browser" }
    & $python @launchArgs
    $code = $LASTEXITCODE
}
if ($code -ne 0 -and $PauseOnError) { Read-Host "Press Enter to close this window" | Out-Null }
exit $code
