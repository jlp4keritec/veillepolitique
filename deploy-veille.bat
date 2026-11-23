@echo off
REM ============================================================
REM deploy-veille.bat - lance deploy-veille.ps1 (debloque le .ps1, policy pour cette fenetre seulement)
REM   1er deploiement : deploy-veille.bat -Init
REM   mise a jour     : deploy-veille.bat
REM   options         : -CopierBase  -SkipNginx  -SkipCertbot
REM ============================================================
setlocal
set "PS1=%~dp0deploy-veille.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -Path '%PS1%' -ErrorAction SilentlyContinue; & '%PS1%' %*; exit $LASTEXITCODE"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo [OK] Deploiement termine.) else (echo [ECHEC] Deploiement arrete - code %RC%. Envoyez une capture de cette fenetre.)
pause
exit /b %RC%
