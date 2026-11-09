# Explicit setup only: public model download; never called by the running app.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -Raw -LiteralPath (Join-Path $root 'backend/embedding-model.json') | ConvertFrom-Json
$folder = Join-Path $root 'backend/models'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$destination = Join-Path $folder 'bge-small-en-v1.5-q8_0.gguf'
function Valid-Model($path) {
    return ((Test-Path -LiteralPath $path) -and
        (Get-Item -LiteralPath $path).Length -eq $manifest.size -and
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $manifest.sha256)
}
if (Valid-Model $destination) { Write-Output 'Local search model is already verified.'; exit 0 }
$partial = Join-Path $folder ('search-' + [guid]::NewGuid().ToString('N') + '.part')
try {
    Invoke-WebRequest -Uri 'https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf/resolve/d32f8c040ea3b516330eeb75b72bcc2d3a780ab7/bge-small-en-v1.5-q8_0.gguf' -OutFile $partial
    if (-not (Valid-Model $partial)) { throw 'Model integrity check failed. Existing model was not replaced.' }
    Move-Item -LiteralPath $partial -Destination $destination -Force
    Write-Output 'Local search model installed and verified.'
} finally {
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial }
}
