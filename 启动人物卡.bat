@echo off
rem D&D 5.5e Character Builder launcher
setlocal
set "SCRIPT=%~dp0dnd55e_character_builder.py"
set "PREF=C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe"
set "MANA=C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe"

if exist "%PREF%" (
    "%PREF%" "%SCRIPT%" %*
    goto :end
)
if exist "%MANA%" (
    "%MANA%" "%SCRIPT%" %*
    goto :end
)
python "%SCRIPT%" %*

:end
if errorlevel 1 (
    echo.
    echo [Error] Failed to start. Make sure Python 3 with tkinter is installed.
    pause
)
endlocal
