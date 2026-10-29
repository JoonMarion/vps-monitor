@echo off
setlocal
cd /d "%~dp0"
echo ======================================================
echo           INICIALIZANDO VPS MONITOR
echo ======================================================

:: 1. Configurar Backend
echo [1/4] Configurando Backend (Python)...
set "BACKEND_PYTHON=%~dp0back-end\.venv\Scripts\python.exe"
if exist "%BACKEND_PYTHON%" goto python_ready
set "BACKEND_PYTHON=%~dp0back-end\venv\Scripts\python.exe"
if exist "%BACKEND_PYTHON%" goto python_ready

set "BACKEND_PYTHON=%~dp0back-end\.venv\Scripts\python.exe"
where py >nul 2>&1
if errorlevel 1 (
    python -m venv "%~dp0back-end\.venv"
) else (
    py -3 -m venv "%~dp0back-end\.venv"
)
if errorlevel 1 goto failed

:python_ready
"%BACKEND_PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 (
    "%BACKEND_PYTHON%" -m ensurepip --upgrade
    if errorlevel 1 goto failed
)
"%BACKEND_PYTHON%" -m pip install --disable-pip-version-check -r "%~dp0back-end\requirements.txt"
if errorlevel 1 goto failed
"%BACKEND_PYTHON%" "%~dp0back-end\configure.py"
if errorlevel 1 goto failed

:: 2. Configurar Frontend
echo [2/4] Configurando Frontend (Node.js)...
if not exist "%~dp0front-end\node_modules" (
    call npm.cmd --prefix "%~dp0front-end" ci
    if errorlevel 1 goto failed
)

:: 3. Rodar Frontend
echo [3/4] Iniciando Dashboard...
echo A dashboard abrira em instantes no seu navegador.
start "VPS Monitor Backend" /D "%~dp0back-end" cmd /k ""%BACKEND_PYTHON%" app.py"
start "VPS Monitor Frontend" /D "%~dp0front-end" cmd /k "npm.cmd run dev -- --open"

echo [4/4] TUDO PRONTO!
echo O backend esta rodando na porta 5000.
echo O frontend esta rodando na porta 5173.
echo Mantenha as janelas abertas enquanto usa o monitor.
echo ======================================================
pause
exit /b 0

:failed
echo.
echo Nao foi possivel iniciar o VPS Monitor. Confira o erro acima.
pause
exit /b 1
