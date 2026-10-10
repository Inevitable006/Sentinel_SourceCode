@echo off
setlocal
cd /d "%~dp0.."
echo === Sentinel: Phase 1 setup ===
echo Moves 'main' up to the finished Phase 0 work, starts branch 'phase1/security'
echo and opens the watcher window. Nothing is pushed to GitHub.
echo.
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "CUR=%%b"
if /i "%CUR%"=="phase1/security" goto :watcher
if /i not "%CUR%"=="phase0/stabilize" (
  echo Current branch is "%CUR%", expected phase0/stabilize. Nothing changed - tell Claude.
  pause
  exit /b 1
)
git merge-base --is-ancestor main phase0/stabilize
if errorlevel 1 (
  echo 'main' has commits that are not in phase0/stabilize. Nothing changed - tell Claude.
  pause
  exit /b 1
)
git branch -f main phase0/stabilize
if errorlevel 1 goto :failed
git switch -c phase1/security
if errorlevel 1 goto :failed

:watcher
echo.
git log --oneline -3
echo.
echo OK: main = Phase 0, you are on branch phase1/security.
call "%~dp0start_watcher.bat"
echo The "Sentinel watcher" window is now open. Leave it open while Claude works.
timeout /t 20
exit /b 0

:failed
echo Something went wrong, see the message above. Nothing was pushed - tell Claude.
pause
exit /b 1
