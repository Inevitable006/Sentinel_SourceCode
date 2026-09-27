@echo off
rem Starts the Sentinel check watcher in its own window. Close that window to stop it.
start "Sentinel watcher" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0watch_checks.ps1"
