@echo off
rem adventurers-folio - new UI launcher (dnd5r kernel + plugins content)
rem Runs from the project root so that --root plugins resolves.
setlocal
pushd "%~dp0"
set "PREF=C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe"
set "MANA=C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe"

if exist "%PREF%" (
    "%PREF%" -m apps.desktop.main %*
    goto :end
)
if exist "%MANA%" (
    "%MANA%" -m apps.desktop.main %*
    goto :end
)
python -m apps.desktop.main %*

:end
if errorlevel 1 (
    echo.
    echo [Error] Failed to start. Requires Python 3 with tkinter.
    echo Run this .bat from the project folder ^(it needs the plugins\ directory^).
    pause
)
popd
endlocal
