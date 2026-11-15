@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem Find Python: normal installation first, then the runtime bundled with DSH.
set "PY="

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
)
if not defined PY if exist "%ProgramFiles%\Python312\python.exe" set "PY=%ProgramFiles%\Python312\python.exe"
if not defined PY if exist "%ProgramFiles%\Python311\python.exe" set "PY=%ProgramFiles%\Python311\python.exe"
if not defined PY if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" (
    set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
)

if not defined PY (
    echo.
    echo Python 3 not found. Install it from https://www.python.org/downloads/
    echo and run this file again.
    echo.
    pause
    exit /b 1
)

"%PY%" -m mtstats serve %*
echo.
pause
