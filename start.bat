@echo off
echo ======================================================
echo           INICIALIZANDO VPS MONITOR
echo ======================================================

:: 1. Configurar Backend
echo [1/4] Configurando Backend (Python)...
cd back-end
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
start "VPS Monitor Backend" cmd /k "venv\Scripts\activate && python app.py"
cd ..

:: 2. Configurar Frontend
echo [2/4] Configurando Frontend (Node.js)...
cd front-end
if not exist node_modules (
    call npm install
)

:: 3. Rodar Frontend
echo [3/4] Iniciando Dashboard...
echo A dashboard abrira em instantes no seu navegador.
start "VPS Monitor Frontend" cmd /k "npm run dev"

echo [4/4] TUDO PRONTO!
echo O backend esta rodando na porta 5000.
echo O frontend esta rodando na porta 5173.
echo Mantenha as janelas abertas enquanto usa o monitor.
echo ======================================================
pause
