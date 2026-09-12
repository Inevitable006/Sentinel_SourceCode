$ErrorActionPreference = "Stop"

Write-Host "Running all Sentinel backend tests..." -ForegroundColor Cyan

$test_files = @(
    "test_policy.py",
    "test_phase8.py",
    "test_phase9.py",
    "test_phase9_security.py",
    "test_research.py",
    "test_phase10_skills.py"
)

$failed = 0

foreach ($file in $test_files) {
    Write-Host "`n============================================================"
    Write-Host "Running $file" -ForegroundColor Yellow
    Write-Host "============================================================"
    
    .venv\Scripts\python $file
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $file returned exit code $LASTEXITCODE" -ForegroundColor Red
        $failed++
    }
    else {
        Write-Host "PASS: $file" -ForegroundColor Green
    }
}

Write-Host "`n============================================================"
if ($failed -eq 0) {
    Write-Host "ALL TESTS PASSED" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "$failed TEST SUITE(S) FAILED" -ForegroundColor Red
    exit 1
}
