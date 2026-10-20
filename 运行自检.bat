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

echo ================ 0/8 local data check ================
"%PY%" _data_sync.py --check
if errorlevel 1 echo [warn] some local data missing - run _data_sync.py when online

echo ================ 1/8 rules + wizard selftest ================
"%PY%" dnd55e_character_builder.py --selftest
if errorlevel 1 goto fail

echo.
echo ================ 2/8 full flow (18 sections) ================
"%PY%" _flowtest.py
if errorlevel 1 goto fail

echo.
echo ================ 3/8 per-level number check (vs SRD 5.2) ================
"%PY%" _resourcecheck.py
if errorlevel 1 goto fail

echo.
echo ================ 4/8 layout audit ================
"%PY%" _layoutcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 5/8 text audit ================
"%PY%" _textcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 6/8 hint clipping check ================
set PYTHONIOENCODING=utf-8
set DND_NO_PAUSE=1
"%PY%" _hintcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 7/8 module dependency check ================
"%PY%" _namecheck.py
if errorlevel 1 goto fail

echo.
echo ================ 8/8 done ================
echo ALL CHECKS PASSED
if not defined DND_NO_PAUSE pause
exit /b 0

:fail
echo.
echo CHECK FAILED - see output above
if not defined DND_NO_PAUSE pause
exit /b 1
