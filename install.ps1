$ErrorActionPreference = 'Stop'
$taskPython = Get-Command python -ErrorAction SilentlyContinue
if (-not $taskPython) { throw 'Python 3.11+ is required.' }
& $taskPython.Source -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ is required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
$taskOldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
    & $taskPython.Source -m codex_bootstrap install
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed.' }
} finally {
    $env:PYTHONPATH = $taskOldPythonPath
}
$taskInstallRecord = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.local/share/codex-auto-bootstrap/installation.json'
$taskInstallation = Get-Content -Raw -LiteralPath $taskInstallRecord | ConvertFrom-Json
$global:CodexAutoBootstrapPython = $taskInstallation.python
function global:codex { & $global:CodexAutoBootstrapPython -B -m codex_bootstrap @args }
$env:PATH = $taskInstallation.bin + [IO.Path]::PathSeparator + $env:PATH
