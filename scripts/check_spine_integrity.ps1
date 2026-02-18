# P0 Spine integrity guardrail: run determinism gate and exit on FAIL.
# Usage: from repo root, .\scripts\check_spine_integrity.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
Push-Location $rootDir
try {
    & python scripts/verify_determinism.py --start 2022-01-01 --end 2022-12-31
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Write-Host "Spine integrity PASS" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "Spine integrity FAIL – do not merge" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}
