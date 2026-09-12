@echo off
set "PYTHON=D:\Anaconda\envs\py100\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Python not found: %PYTHON%
    echo   Run: conda create -n py100 python=3.11
    pause
    exit /b 1
)

"%PYTHON%" "%~dp0main.py" %*
if errorlevel 1 pause
