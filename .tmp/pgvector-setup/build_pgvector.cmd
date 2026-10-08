@echo off
call D:\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if errorlevel 1 exit /b %errorlevel%
set "PGROOT=C:\Program Files\PostgreSQL\17"
nmake /F Makefile.win
