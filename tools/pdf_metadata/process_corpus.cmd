@echo off
chcp 65001 >nul
where pwsh.exe >nul 2>nul
if errorlevel 1 (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0process_corpus.ps1" "%~1" -Open
) else (
  pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0process_corpus.ps1" "%~1" -Open
)
if errorlevel 1 pause
