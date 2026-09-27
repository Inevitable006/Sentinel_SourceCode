# Sentinel verification run (Windows).
# Writes everything to docs\runs\latest.txt (and a timestamped copy).
#   tools\check.bat                  -> all steps
#   tools\check.bat -Only tests      -> one step: env | tests | smoke | electron | gpu
#   tools\check_quick.bat            -> tests + smoke + electron (no GPU benchmark)
#   tools\check.bat -Only deps       -> install pinned Python packages (not part of 'all')
# Read-only for your data: the smoke test uses an isolated temp data folder.
param([string]$Only = "all")
$ErrorActionPreference = "Continue"
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
function Stop-SentinelProcs {
  Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_server.py*' -and $_.CommandLine -like '*Sentinel_SourceCode*') -or
    ($_.Name -eq 'electron.exe' -and $_.ExecutablePath -like '*Sentinel_SourceCode*')
  } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "stopped $($_.Name) pid $($_.ProcessId)" }
}

& {
  Section "RUN $(Get-Date -Format o)  (-Only $Only)"
  Set-Location $root
  git log -1 --oneline; "changed files: " + ((git status --short) | Measure-Object).Count

  if ($Only -eq "deps") {
    Section "PIP: install pinned backend requirements into backend\.venv"
    & $py -m pip install --disable-pip-version-check -r (Join-Path $root "backend\requirements.txt")
    "pip install exit code: $LASTEXITCODE"
    & $py -m pip check; "pip check exit code: $LASTEXITCODE"
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
    "pytest exit code: $LASTEXITCODE"
    Section "SCRIPT test_phase8.py (isolated data dir)"
    $realAppData = $env:APPDATA
    $env:APPDATA = Join-Path $env:TEMP ("sentinel_phase8_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force (Join-Path $env:APPDATA "sentinel\models") | Out-Null
    & $py tests\integration\test_phase8.py; "exit code: $LASTEXITCODE"
    $env:APPDATA = $realAppData
    Section "FRONTEND typecheck + build"
    Set-Location (Join-Path $root "frontend"); npm run build 2>&1 | Where-Object { $_ -notmatch 'npm notice' }
    "build exit code: $LASTEXITCODE"
    Set-Location (Join-Path $root "src\main"); node --check main.js; node --check preload.js; "node --check exit code: $LASTEXITCODE"
  }

  if (Want "smoke") {
    Section "SMOKE: backend + model + websocket chat (isolated data dir)"
    Set-Location $root
    & $py tools\smoke_chat.py
    "smoke exit code: $LASTEXITCODE"
    Stop-SentinelProcs
  }

  if (Want "electron") {
    Section "ELECTRON: start app (production UI), auto-quit after 35s"
    Set-Location $root
    $exe = Join-Path $root "node_modules\electron\dist\electron.exe"
    $log = Join-Path $env:TEMP "sentinel_electron_smoke.log"
    $env:SENTINEL_SMOKE_QUIT_AFTER_MS = "35000"
    $env:ELECTRON_ENABLE_LOGGING = "1"   # print renderer console messages
    $p = Start-Process -FilePath $exe -ArgumentList "." -WorkingDirectory $root -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru
    Remove-Item Env:\SENTINEL_SMOKE_QUIT_AFTER_MS, Env:\ELECTRON_ENABLE_LOGGING
    $exited = $p.WaitForExit(60000)
    "electron quit cleanly by itself within 60s: $exited (exit code: $(if ($exited) { $p.ExitCode } else { 'n/a' }))"
    Get-Content $log, "$log.err" -ErrorAction SilentlyContinue |
      ForEach-Object { $_ -replace 'token=[0-9a-fA-F]+', 'token=<redacted>' } |
      Select-String -Pattern 'SENTINEL|Python AI|WebSocket|rror|security|Blocked|Uvicorn|Refused|CONSOLE' | Select-Object -Last 60 | ForEach-Object { $_.Line }
    Stop-SentinelProcs
  }

  if (Want "gpu") {
    Section "GPU PROBE: bundled llama.cpp (backend\llama-bin.zip) with CUDA"
    $zip = Join-Path $root "backend\llama-bin.zip"
    $dst = Join-Path $env:TEMP "sentinel_llama_probe"
    if (-not (Test-Path (Join-Path $dst "llama-bench.exe"))) { Expand-Archive -Path $zip -DestinationPath $dst -Force }
    $nv = Join-Path $root "backend\.venv\Lib\site-packages\nvidia"
    $env:PATH = "$dst;$nv\cuda_runtime\bin;$nv\cublas\bin;$env:PATH"
    (Get-FileHash (Join-Path $dst "llama-server.exe") -Algorithm SHA256).Hash
    (Get-FileHash $zip -Algorithm SHA256).Hash + "  llama-bin.zip"
    & "$dst\llama-server.exe" --version 2>&1
    & "$dst\llama-server.exe" --list-devices 2>&1
    $m = "$env:APPDATA\sentinel\models"
    & "$dst\llama-bench.exe" -m "$m\qwen2.5-1.5b-instruct-q4_k_m.gguf" -ngl 0,99 -p 256 -n 64 -r 2 2>&1
    & "$dst\llama-bench.exe" -m "$m\qwen2.5-7b-instruct-q4_k_m.gguf" -ngl 99 -p 256 -n 64 -r 2 2>&1
  }
  Section "DONE $(Get-Date -Format o)"
} *>&1 | Out-File -Encoding utf8 $out
Copy-Item $out (Join-Path $runs ("check_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".txt"))
Write-Host "Done. Results in $out"
