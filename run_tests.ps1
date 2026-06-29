$python = "C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$depsPath = Join-Path $projectRoot ".pydeps"

if (-not (Test-Path $python)) {
    Write-Error "Fallback Python not found at $python"
    exit 1
}

$code = @'
import sys
import unittest

project_root = r"__PROJECT_ROOT__"
deps_path = r"__DEPS_PATH__"

sys.path.insert(0, project_root)
sys.path.insert(0, deps_path)

suite = unittest.defaultTestLoader.discover("tests")
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
'@

$code = $code.Replace("__PROJECT_ROOT__", $projectRoot).Replace("__DEPS_PATH__", $depsPath)
$code | & $python -
