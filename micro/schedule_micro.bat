@echo off
REM Cree une tache Windows qui lance run_micro.bat toutes les 30 minutes,
REM du lundi au vendredi, de 9 h 30 a 16 h (heure LOCALE du PC : le PC doit
REM etre a l'heure de Montreal / Eastern). Argent fictif seulement.
REM   schedule_micro.bat            creer / mettre a jour la tache
REM   schedule_micro.bat remove     supprimer la tache
REM Les resultats s'ajoutent a micro_paper.log dans ce dossier.
cd /d "%~dp0"
set TASK=TradeMarketMicroPaper

if /i "%~1"=="remove" (
    schtasks /Delete /TN %TASK% /F
    exit /b %errorlevel%
)

schtasks /Create /F /TN %TASK% /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:30 ^
    /RI 30 /DU 06:31 /TR "\"%~dp0run_micro.bat\""
if errorlevel 1 (
    echo Echec de creation de la tache. Essayez en tant qu'administrateur.
    pause
    exit /b 1
)
echo.
echo Tache "%TASK%" creee : run_micro.bat toutes les 30 min, lun-ven 9:30-16:00.
echo Test immediat :  schtasks /Run /TN %TASK%
echo Rapport       :  run_micro.bat --rapport
pause
