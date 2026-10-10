# Sentinel verification run (Windows).
# Writes everything to docs\runs\latest.txt (and a timestamped copy).
#   tools\check.bat                  -> all steps
#   tools\check.bat -Only tests      -> one step: env | tests | smoke | electron | gpu
#   tools\check_quick.bat            -> tests + smoke + electron (no GPU benchmark)
#   tools\check.bat -Only deps       -> install pinned Python packages (not part of 'all')
#   tools\check.bat -Only pytest     -> backend tests only (fast)
#   tools\check.bat -Only probe      -> which packages have wheels for this Python (installs nothing)
# Read-only for your data: the smoke test uses an isolated temp data folder.
param([ValidateSet("all", "quick", "env", "tests", "pytest", "probe", "deps", "smoke", "electron", "gpu")][string]$Only = "all")
$ErrorActionPreference = "Continue"
$script:checkFailed = $false
$initialErrorCount = $Error.Count
function Record-Result([string]$label, [int]$code) {
  if ($code -ne 0) { $script:checkFailed = $true }
  "${label} exit code: $code"
}
$root  = Split-Path -Parent $PSScriptRoot
$runs  = Join-Path $root "docs\runs"
$out   = Join-Path $runs "latest.txt"
$py    = Join-Path $root "backend\.venv\Scripts\python.exe"
New-Item -ItemType Directory -Force $runs | Out-Null
function Want($s) {
  if ($Only -eq "quick") { return @("tests", "smoke", "electron") -contains $s }
  return ($Only -eq "all" -or $Only -eq $s)
}
function Section($t) { "`n==================== $t ====================" }
function Get-SentinelProcs {
  Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_server.py*' -and $_.CommandLine -like '*Sentinel_SourceCode*') -or
    ($_.Name -eq 'electron.exe' -and $_.ExecutablePath -like '*Sentinel_SourceCode*')
  }
}
function Stop-SentinelProcs {
  Get-SentinelProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "stopped $($_.Name) pid $($_.ProcessId)" }
}
# The owner's running Sentinel is never closed by a check: smoke/electron are skipped while it is open.
function Get-BusyNote([string]$what) {
  $p = @(Get-SentinelProcs)
  if ($p.Count -gt 0) { return "SKIPPED ${what}: Sentinel is open (pid $(($p | ForEach-Object { $_.ProcessId }) -join ', ')). Close it, then ask again." }
  return ""
}

& {
  Section "RUN $(Get-Date -Format o)  (-Only $Only)"
  Set-Location $root
  git log -1 --oneline; "changed files: " + ((git status --short) | Measure-Object).Count

  if ($Only -eq "pytest") {
    Section "PYTEST backend/tests (fast run: backend only)"
    Set-Location (Join-Path $root "backend"); $env:PYTHONPATH = (Join-Path $root "backend")
    & $py -m pytest tests -q -rfEs --tb=short -p no:cacheprovider -W ignore::DeprecationWarning
    Record-Result "pytest" $LASTEXITCODE
  }

  if ($Only -eq "probe") {
    Section "PROBE: ready-made wheels for this Python (downloads to TEMP, installs nothing)"
    $probeDir = Join-Path $env:TEMP "sentinel_probe"
    New-Item -ItemType Directory -Force $probeDir | Out-Null
    foreach ($pkg in @("sqlcipher3-wheels", "sqlcipher3-binary", "apsw-sqlite3mc", "cryptography", "nvidia-ml-py", "argon2-cffi-bindings")) {
      $o = & $py -m pip download --disable-pip-version-check --no-deps --only-binary=:all: --dest $probeDir $pkg 2>&1 | Out-String
      $w = [regex]::Match($o, '([^\\/\s]+\.whl)').Groups[1].Value
      if ($w) { "OK    $pkg -> $w" } else { "NONE  $pkg -> " + ((($o -split "`n") | Where-Object { $_ -match 'ERROR' } | Select-Object -First 1)) }
    }
  }

  if ($Only -eq "deps") {
    Section "PIP: install pinned backend requirements into backend\.venv"
    & $py -m pip install --disable-pip-version-check -r (Join-Path $root "backend\requirements.txt")
    Record-Result "pip install" $LASTEXITCODE
    & $py -m pip check; Record-Result "pip check" $LASTEXITCODE
    Section "PIP FREEZE"; & $py -m pip freeze
  }

  if (Want "env") {
    Section "PYTHON"; & $py -c "import sys;print(sys.version)"
    Section "LLAMA_CPP (python binding)"
    & $py -c "import llama_cpp;print('version',llama_cpp.__version__);print('gpu_offload',llama_cpp.llama_supports_gpu_offload())"
    Section "GPU"; nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv
    Section "MODELS"
    Get-ChildItem "$env:APPDATA\sentinel\models" -ErrorAction SilentlyContinue | ForEach-Object { "{0}  {1:N0} MB" -f $_.Name, ($_.Length/1MB) }
    Section "NODE"; node -v
  }

  if (Want "tests") {
    Section "PYTEST backend/tests"
    Set-Location (Join-Path $root "backend"); $env:PYTHONPATH = (Join-Path $root "backend")
    & $py -m pytest tests -q -rfEs --tb=short -p no:cacheprovider --continue-on-collection-errors -W ignore::DeprecationWarning
    Record-Result "pytest" $LASTEXITCODE
    Section "SCRIPT test_phase8.py (isolated data dir)"
    $realAppData = $env:APPDATA
    $env:APPDATA = Join-Path $env:TEMP ("sentinel_phase8_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force (Join-Path $env:APPDATA "sentinel\models") | Out-Null
    & $py tests\integration\test_phase8.py; Record-Result "phase8" $LASTEXITCODE
    $env:APPDATA = $realAppData
    Section "FRONTEND typecheck + build"
    Set-Location (Join-Path $root "frontend"); npm run build 2>&1 | Where-Object { $_ -notmatch 'npm notice' }
    Record-Result "build" $LASTEXITCODE
    Set-Location (Join-Path $root "src\main")
    node --check main.js; Record-Result "main.js syntax" $LASTEXITCODE
    node --check preload.js; Record-Result "preload.js syntax" $LASTEXITCODE
    Set-Location $root
    Section "VOICE: WAV encoding and microphone permission boundaries"
    node --test tools/tests/voice.test.mjs; Record-Result "voice JavaScript tests" $LASTEXITCODE
    node --test tools/tests/safe-mode.test.mjs; Record-Result "safe-mode JavaScript tests" $LASTEXITCODE
    node --test tools/tests/os-lock.test.mjs; Record-Result "OS lock JavaScript tests" $LASTEXITCODE
    node --test tools/tests/packaging.test.mjs; Record-Result "packaging JavaScript tests" $LASTEXITCODE
  }

  if (Want "smoke") {
    Section "SMOKE: backend + model + websocket chat (isolated data dir)"
    $busy = Get-BusyNote "smoke"
    if ($busy) { $busy } else {
      Set-Location $root
      & $py tools\smoke_chat.py
      Record-Result "smoke" $LASTEXITCODE
      Stop-SentinelProcs
    }
  }

  if (Want "electron") {
    Section "ELECTRON: start app (production UI), auto-quit after 35s"
    $busy = Get-BusyNote "electron"
    if ($busy) { $busy } else {
    Set-Location $root
    $exe = Join-Path $root "node_modules\electron\dist\electron.exe"
    $log = Join-Path $env:TEMP "sentinel_electron_smoke.log"
    $env:SENTINEL_SMOKE_QUIT_AFTER_MS = "35000"
    $env:ELECTRON_ENABLE_LOGGING = "1"   # print renderer console messages
    $p = Start-Process -FilePath $exe -ArgumentList "." -WorkingDirectory $root -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru
    $null = $p.Handle   # without reading the handle now, PowerShell later reports an empty ExitCode
    Remove-Item Env:\SENTINEL_SMOKE_QUIT_AFTER_MS, Env:\ELECTRON_ENABLE_LOGGING
    $exited = $p.WaitForExit(60000)
    if (-not $exited -or $p.ExitCode -ne 0) { $script:checkFailed = $true }
    "electron quit cleanly by itself within 60s: $exited (exit code: $(if ($exited) { $p.ExitCode } else { 'n/a' }))"
    Get-Content $log, "$log.err" -ErrorAction SilentlyContinue |
      ForEach-Object { $_ -replace 'token=[0-9a-fA-F]+', 'token=<redacted>' } |
      Select-String -Pattern 'SENTINEL|Python AI|WebSocket|rror|security|Blocked|Uvicorn|Refused|CONSOLE' | Select-Object -Last 60 | ForEach-Object { $_.Line }
    Stop-SentinelProcs
    }
  }

  if (Want "gpu") {
    # Starts Sentinel's own GPU engine (hash-checked llama-server) for each downloaded model.
    Section "GPU ENGINE BENCHMARK (tools\bench_gpu.py)"
    & $py (Join-Path $root "tools\bench_gpu.py") 2>&1
    Record-Result "bench" $LASTEXITCODE
  }
  Section "DONE $(Get-Date -Format o)"
} *>&1 | Out-File -Encoding utf8 $out
Copy-Item $out (Join-Path $runs ("check_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".txt"))
if ($script:checkFailed -or $Error.Count -gt $initialErrorCount) {
  Write-Host "FAILED. Results in $out"
  exit 1
}
Write-Host "Completed. Results in $out (review any skipped checks)."
exit 0
