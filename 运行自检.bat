@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem 界面文案含 ✓ 等符号, Windows 默认 GBK 下 print 会 UnicodeEncodeError
set PYTHONIOENCODING=utf-8
set DND_NO_PAUSE=1

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

echo ================ 0/10 local data check ================
"%PY%" tools\legacy\_data_sync.py --check
if errorlevel 1 echo [warn] some local data missing - run _data_sync.py when online

echo ================ 1/10 rules + wizard selftest ================
"%PY%" dnd55e_character_builder.py --selftest
if errorlevel 1 goto fail

echo.
echo ================ 2/10 full flow (19 sections) ================
"%PY%" tools\legacy\_flowtest.py
if errorlevel 1 goto fail

echo.
echo ================ 3/10 per-level number check (vs SRD 5.2) ================
"%PY%" tools\legacy\_resourcecheck.py
if errorlevel 1 goto fail

echo.
echo ================ 4/10 layout audit ================
"%PY%" tools\legacy\_layoutcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 5/10 text audit ================
"%PY%" tools\legacy\_textcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 6/10 hint clipping check ================
"%PY%" tools\legacy\_hintcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 7/10 summon stat block check ================
"%PY%" tools\legacy\_summoncheck.py
if errorlevel 1 goto fail

echo.
echo ================ 8/10 module dependency check ================
"%PY%" tools\legacy\_namecheck.py
if errorlevel 1 goto fail

echo.
echo ================ 9/10 invocation / attack rider data check ================
"%PY%" tools\legacy\_invocheck.py
if errorlevel 1 goto fail

echo.
echo ================ 10/10 done ================
echo ALL CHECKS PASSED
if not defined DND_NO_PAUSE pause
exit /b 0

:fail
echo.
echo CHECK FAILED - see output above
if not defined DND_NO_PAUSE pause
exit /b 1
