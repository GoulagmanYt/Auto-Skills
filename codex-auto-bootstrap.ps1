$taskPreviousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = (Join-Path $PSScriptRoot 'src')
    if ($taskPreviousPythonPath) { $env:PYTHONPATH += [IO.Path]::PathSeparator + $taskPreviousPythonPath }
    & python -m codex_bootstrap @args
    exit $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $taskPreviousPythonPath
}
