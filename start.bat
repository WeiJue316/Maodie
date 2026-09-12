@echo off
chcp 65001 >nul 2>&1
title Project Agent v2

echo ========================================
echo   Project Agent v2 - Starting...
echo ========================================
echo.

:: Kill any existing processes on ports 8000 and 5173
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1

echo [1/2] Starting backend (port 8000)...
cd /d "D:\Project\py pr\project_class"
start "Backend" /min cmd /k "D:\Anaconda\envs\py100\python.exe main.py --web --port 8000"

echo [2/2] Starting frontend (port 5173)...
cd /d "D:\Project\py pr\project_class\frontend"
start "Frontend" /min cmd /k "npx vite --host"

echo.
echo ========================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   API Docs: http://localhost:8000/docs
echo ========================================
echo.
echo Waiting for servers to start...
timeout /t 5 /nobreak >nul
start http://localhost:5173
echo Done! Browser opened.
pause
