@echo off
REM Bot de PRATIQUE micro (argent fictif, aucun ordre reel).
REM   run_micro.bat             une passe (rien hors des heures de marche)
REM   run_micro.bat --force     une passe meme hors des heures de marche
REM   run_micro.bat --rapport   solde, profit net apres frais, liste des trades
REM Utilise Python 3.12 (lanceur "py"). Installe yfinance au besoin.
cd /d "%~dp0"

set "PY=python"
py -3.12 --version >nul 2>nul && set "PY=py -3.12"

%PY% -c "import yfinance, pandas" 2>nul
if errorlevel 1 (
    echo Installation de yfinance / pandas...
    REM versions du requirements.txt : numpy 2.5 est bloque par le controle des applications Windows sur ce PC
    %PY% -m pip install --quiet "pandas==2.2.2" "numpy<2.1" "yfinance==0.2.66" || goto :fail
)

%PY% micro_paper.py %*
exit /b %errorlevel%

:fail
echo Python 3.12 introuvable. Installez-le depuis https://www.python.org/downloads/
exit /b 1
