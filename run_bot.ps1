$python = "C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$depsPath = Join-Path $projectRoot ".pydeps"

if (-not (Test-Path $python)) {
    Write-Error "Fallback Python not found at $python"
    exit 1
}

$env:PYTHONPATH = "$projectRoot;$depsPath"
& $python bot.py
