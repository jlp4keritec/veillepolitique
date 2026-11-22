@echo off
REM ============================================================
REM start-backend.cmd - Lance le backend VEILLE (FastAPI) en local
REM 1. Cherche Python 3.14, puis 3.13, puis 3.12
REM 2. Cree l'environnement Python backend\.venv si absent
REM 3. Cree ou complete backend\.env - vos cles ne sont jamais ecrasees
REM 4. Cree la base SQLite et ajoute les sources par defaut - idempotent
REM 5. Verifie que le port 8710 est libre
REM 6. Demarre l'API sur http://127.0.0.1:8710
REM ============================================================
setlocal
set "PORT=8710"
cd /d "%~dp0backend"

if exist ".venv\Scripts\python.exe" goto ready

set "PY="
for %%V in (3.14 3.13 3.12) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,14) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython

echo [..] Python trouve : %PY%
echo [..] Creation de l'environnement Python - premiere fois, patientez...
if exist ".venv" rmdir /s /q ".venv"
%PY% -m venv .venv
if errorlevel 1 goto err
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto err

:ready
echo [..] Configuration backend\.env...
".venv\Scripts\python.exe" scripts\init_env.py
if errorlevel 1 goto err

echo [..] Base de donnees et sources par defaut...
".venv\Scripts\python.exe" scripts\init_db.py
if errorlevel 1 goto err

netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 goto portbusy

echo.
echo [OK] Backend sur http://127.0.0.1:%PORT%  - sante : /api/v1/health  - doc : /docs
echo      Ctrl+C pour arreter.
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload
goto end

:portbusy
echo.
echo [ERREUR] Le port %PORT% est deja utilise par un autre programme.
echo          Programme concerne - colonne PID :
netstat -ano | findstr /R /C:":%PORT% .*LISTENING"
echo          Fermez-le, ou changez PORT en haut de ce script.
pause
exit /b 1

:nopython
echo.
echo [ERREUR] Aucune version compatible de Python : il faut 3.12, 3.13 ou 3.14.
echo          Versions detectees sur ce PC :
py --list 2>nul
echo.
echo          Installez Python 3.14 depuis https://www.python.org/downloads/
echo          en cochant "Add python.exe to PATH", puis relancez ce script.
pause
exit /b 1

:err
echo.
echo [ERREUR] Une etape a echoue. Lisez le message ci-dessus.
pause
exit /b 1

:end
endlocal
