# Builds the portable Python runtime that the installed app uses (resources\python).
# Offline: it uses files you downloaded yourself and verifies them; it downloads nothing.
#
# 1. Download the Windows "embeddable package (64-bit)" for the SAME Python version as
#    backend\.venv (python -V) from python.org, and note its published SHA-256.
# 2. Download the wheels once (this step uses the internet, run it yourself):
#      backend\.venv\Scripts\python -m pip download -r backend\requirements.txt -d build\wheelhouse --only-binary=:all:
# 3. Run:
#      powershell -ExecutionPolicy Bypass -File tools\build_runtime.ps1 -EmbedZip <path-to-zip> -Sha256 <hash>
# 4. Then build the installer:  npm run dist
param(
  [Parameter(Mandatory = $true)][string]$EmbedZip,
  [Parameter(Mandatory = $true)][string]$Sha256,
  [string]$Wheelhouse = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root "build\python-runtime"
if (-not $Wheelhouse) { $Wheelhouse = Join-Path $root "build\wheelhouse" }
$devPython = Join-Path $root "backend\.venv\Scripts\python.exe"

$actual = (Get-FileHash -Algorithm SHA256 $EmbedZip).Hash.ToLower()
if ($actual -ne $Sha256.ToLower()) { throw "Embeddable zip SHA-256 mismatch: expected $Sha256, got $actual" }
if (-not (Test-Path $Wheelhouse)) { throw "Wheel folder not found: $Wheelhouse (see step 2 above)" }

$devVersion = (& $devPython -c "import sys;print('%d%d' % sys.version_info[:2])").Trim()
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
Expand-Archive -Path $EmbedZip -DestinationPath $out
$pth = Get-ChildItem $out -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "Not an embeddable package: no python*._pth file" }
if ($pth.Name -ne "python$devVersion._pth") { throw "Version mismatch: runtime $($pth.Name), backend venv python$devVersion" }

# Module search path of the installed app: standard library, its packages, and the backend.
@("python$devVersion.zip", ".", "Lib\site-packages", "..\backend") | Set-Content -Encoding ascii $pth.FullName

& $devPython -m pip install --disable-pip-version-check --no-index --find-links $Wheelhouse `
  --target (Join-Path $out "Lib\site-packages") -r (Join-Path $root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install into the runtime failed" }

# Smoke: the runtime can import the backend without the developer venv.
Push-Location (Join-Path $root "backend")
try {
  $env:APPDATA = Join-Path $env:TEMP ("sentinel_runtime_check_" + [guid]::NewGuid().ToString("N"))
  # (Installed, ..\backend in the ._pth file resolves to resources\backend; here we add it explicitly.)
  $backend = (Join-Path $root "backend")
  & (Join-Path $out "python.exe") -c "import sys; sys.path.insert(0, r'$backend'); import app.main, uvicorn; print('runtime OK')"
  if ($LASTEXITCODE -ne 0) { throw "The portable runtime cannot import the backend" }
} finally { Pop-Location }
Write-Host "Portable runtime ready in $out"
