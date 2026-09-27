# Sentinel check watcher (Windows). Start it with tools\start_watcher.bat and leave the window open.
#
# Claude writes docs\runs\request.txt. Only its FIRST LINE is read, and it must be one of:
#   quick | tests | smoke | electron | env | gpu | all | deps  -> runs tools\check.ps1 -Only <that word>
#   status                                                     -> branch, changed files, last commits
#   commit                                                     -> git add -A + git commit -F docs\runs\commit_msg.txt
#                                                                 (refused on main / detached HEAD; never pushes)
# Nothing from the request file is ever executed. Unknown words are ignored.
# Progress: docs\runs\watcher_status.txt   Results: docs\runs\latest.txt   (docs\runs is git-ignored)
# If this script file changes, the watcher checks the new version for syntax errors and restarts itself with it.
# Stop: close this window (or press Ctrl+C).
param([int]$PollSeconds = 3)
$ErrorActionPreference = "Continue"
$root    = Split-Path -Parent $PSScriptRoot
$runs    = Join-Path $root "docs\runs"
$request = Join-Path $runs "request.txt"
$status  = Join-Path $runs "watcher_status.txt"
$out     = Join-Path $runs "latest.txt"
$msgFile = Join-Path $runs "commit_msg.txt"
$checks  = @("quick", "tests", "smoke", "electron", "env", "gpu", "all", "deps")
$self    = $PSCommandPath
$selfHash = (Get-FileHash $self).Hash
New-Item -ItemType Directory -Force $runs | Out-Null

function Set-Status([string]$s) { "$s | $(Get-Date -Format o)" | Out-File -Encoding utf8 $status }

$Host.UI.RawUI.WindowTitle = "Sentinel watcher"
Write-Host "Sentinel watcher running for $root"
Write-Host "Leave this window open while Claude works. Close it to stop."
Set-Status "idle"

while ($true) {
  # Self-update: restart with the new version only if it parses cleanly.
  $h = (Get-FileHash $self -ErrorAction SilentlyContinue).Hash
  if ($h -and $h -ne $selfHash) {
    $errs = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($self, [ref]$null, [ref]$errs)
    if ($errs.Count -eq 0) {
      Set-Status "restarting (watcher updated)"
      Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$self`""
      exit
    }
    Set-Status "update has syntax errors - still running the previous version"
    $selfHash = $h
  }

  if (Test-Path $request) {
    $action = ""
    try { $action = ([string](Get-Content $request -TotalCount 1)).Trim().ToLower() } catch { }
    Remove-Item $request -Force -ErrorAction SilentlyContinue
    $time = Get-Date -Format T
    if ($checks -contains $action) {
      Write-Host "$time  check: $action"
      Set-Status "running $action"
      & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check.ps1") -Only $action
      Set-Status "done $action"
    }
    elseif ($action -eq "status" -or $action -eq "commit") {
      Write-Host "$time  git: $action"
      Set-Status "running $action"
      Set-Location $root
      & {
        "==================== GIT $action $(Get-Date -Format o) ===================="
        $branch = (git rev-parse --abbrev-ref HEAD | Out-String).Trim()
        "branch: $branch"
        if ($action -eq "commit") {
          if (@("main", "master", "HEAD") -contains $branch) { "REFUSED: the watcher never commits on '$branch'." }
          elseif (-not (Test-Path $msgFile)) { "REFUSED: docs\runs\commit_msg.txt is missing." }
          else {
            git add -A
            git commit -F $msgFile
            "commit exit code: $LASTEXITCODE"
            Move-Item $msgFile "$msgFile.used" -Force   # a message is used once
          }
        }
        "--- changed files"; git status --short
        "--- last commits"; git log --oneline -5
        "==================== DONE $(Get-Date -Format o) ===================="
      } *>&1 | Out-File -Encoding utf8 $out
      Set-Status "done $action"
    }
    elseif ($action -ne "") {
      Write-Host "$time  ignored unknown request"
      Set-Status "ignored unknown request"
    }
  }
  Start-Sleep -Seconds $PollSeconds
}
