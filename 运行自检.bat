@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY=C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python not found.
        pause
        exit /b 1
    )
    set "PY=python"
)

echo ================ 0/7 local data check ================
"%PY%" _data_sync.py --check
if errorlevel 1 echo [warn] some local data missing - run _data_sync.py when online

echo ================ 1/7 rules + wizard selftest ================
"%PY%" dnd55e_character_builder.py --selftest
if errorlevel 1 goto fail

echo.
echo ================ 2/7 full flow (18 sections) ================
"%PY%" _flowtest.py
if errorlevel 1 goto fail

echo.
echo ================ 3/7 per-level number check (vs SRD 5.2) ================
"%PY%" _resourcecheck.py
if errorlevel 1 goto fail

echo.
echo ================ 4/7 layout audit ================
"%PY%" _layoutcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 5/7 text audit ================
"%PY%" _textcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 6/7 module dependency check ================
"%PY%" _namecheck.py
if errorlevel 1 goto fail

echo.
echo ================ 7/7 done ================
echo ALL CHECKS PASSED
if not defined DND_NO_PAUSE pause
exit /b 0

:fail
echo.
echo CHECK FAILED - see output above
if not defined DND_NO_PAUSE pause
exit /b 1
