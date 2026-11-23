@echo off
REM ============================================================
REM relancer-tout.cmd - Redemarre VEILLE en local
REM 1. Ferme le backend - port 8710
REM 2. Lance les tests du backend - s'arrete s'ils echouent
REM 3. Relance le backend, attend qu'il reponde
REM 4. Ouvre la page d'accueil dans le navigateur
REM Ne touche qu'au port de ce projet.
REM Le frontend sera ajoute a ce script en phase dashboard.
REM ============================================================
setlocal
cd /d "%~dp0"
set "BACK=8710"

echo [..] Fermeture de la fenetre precedente...
taskkill /FI "WINDOWTITLE eq VEILLE-backend*" /T /F >nul 2>nul
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%BACK% .*LISTENING"') do taskkill /PID %%p /T /F >nul 2>nul
ping -n 3 127.0.0.1 >nul
netstat -ano | findstr /R /C:":%BACK% .*LISTENING" >nul
if not errorlevel 1 goto stillbusy
echo [OK] Backend arrete.

echo.
echo [..] Tests du backend...
call "%~dp0test-backend.cmd" nopause
if errorlevel 1 goto testsfail

echo.
echo [..] Demarrage du backend...
start "VEILLE-backend" cmd /c "%~dp0start-backend.cmd"
for /L %%i in (1,1,90) do (
    curl.exe -s -o nul http://127.0.0.1:%BACK%/api/v1/health && goto backok
    ping -n 2 127.0.0.1 >nul
)
goto backfail

:backok
echo [OK] Backend pret sur http://127.0.0.1:%BACK%
start "" http://127.0.0.1:%BACK%/
echo.
echo La fenetre VEILLE-backend reste ouverte.
echo Pour arreter : relancez ce script ou fermez cette fenetre.
ping -n 4 127.0.0.1 >nul
exit /b 0

:stillbusy
echo.
echo [ERREUR] Le port %BACK% est encore occupe :
netstat -ano | findstr /R /C:":%BACK% .*LISTENING"
echo          Fermez le programme concerne - colonne PID - puis relancez.
pause
exit /b 1

:testsfail
echo.
echo [ECHEC] Des tests ont echoue : l'application n'est PAS relancee.
echo         Envoyez une capture de cette fenetre.
pause
exit /b 1

:backfail
echo.
echo [ERREUR] Le backend ne repond pas apres 3 minutes.
echo          Regardez la fenetre VEILLE-backend.
pause
exit /b 1
