@echo off
REM ============================================================
REM test-backend.cmd - Lance tous les tests du backend VEILLE
REM Les tests utilisent une base temporaire - jamais la vraie base.
REM Les tests doivent tous passer avant une livraison.
REM Option : test-backend.cmd nopause - sans pause finale, pour relancer-tout.cmd
REM ============================================================
setlocal
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Environnement absent : lancez d'abord start-backend.cmd
    if /i not "%~1"=="nopause" pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\init_env.py >nul
".venv\Scripts\python.exe" -m pytest
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo [OK] Tous les tests passent.
) else (
    echo [ECHEC] Des tests ont echoue - code %RC%.
)
if /i not "%~1"=="nopause" pause
exit /b %RC%
