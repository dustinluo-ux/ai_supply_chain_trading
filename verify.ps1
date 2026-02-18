# verify.ps1
# Run this after every main.py execution

param(
    [string]$Mode = "backtest"
)

# Check prerequisites FIRST
Write-Host "`n=== CHECKING PREREQUISITES ===" -ForegroundColor Cyan

$techIndicators = Get-ChildItem -Path "data/signals/technical_indicators_*.csv" -ErrorAction SilentlyContinue
if (-not $techIndicators) {
    Write-Host "WARNING: No technical indicators found. Run with warmup or generate signals first." -ForegroundColor Yellow
} else {
    Write-Host "OK: Technical indicators exist: $($techIndicators[-1].Name)" -ForegroundColor Green
}

# Now verify outputs
Write-Host "`n=== VERIFICATION START ===" -ForegroundColor Cyan

$errors = @()

# Check logs exist
$logPattern = "logs/ai_supply_chain_*.log"
$logs = Get-ChildItem -Path $logPattern -ErrorAction SilentlyContinue
if (-not $logs) {
    $errors += "FAIL: No log file found matching $logPattern"
} else {
    Write-Host "OK: Log file exists: $($logs[-1].Name)" -ForegroundColor Green
}

if ($Mode -eq "backtest") {
    # Check backtest outputs
    $perfPattern = "backtests/performance_*.csv"
    $perf = Get-ChildItem -Path $perfPattern -ErrorAction SilentlyContinue
    if (-not $perf) {
        $errors += "FAIL: No performance CSV found"
    } else {
        Write-Host "OK: Performance CSV exists: $($perf[-1].Name)" -ForegroundColor Green
    }
    
    # Check signals
    $signalPattern = "data/signals/combined_scores_*.csv"
    $signals = Get-ChildItem -Path $signalPattern -ErrorAction SilentlyContinue
    if (-not $signals) {
        $errors += "FAIL: No signal CSV found"
    } else {
        Write-Host "OK: Signals CSV exists: $($signals[-1].Name)" -ForegroundColor Green
    }
}

if (($Mode -eq "live") -or ($Mode -eq "paper")) {
    # Check trade outputs
    if (-not (Test-Path "outputs/trades_*.csv")) {
        $errors += "FAIL: No trades CSV found"
    } else {
        Write-Host "OK: Trades CSV exists" -ForegroundColor Green
    }
}

# Report
if ($errors.Count -eq 0) {
    Write-Host "`n=== VERIFICATION PASSED ===" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n=== VERIFICATION FAILED ===" -ForegroundColor Red
    foreach ($err in $errors) {
        Write-Host $err -ForegroundColor Red
    }
    exit 1
}