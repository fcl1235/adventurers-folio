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

echo ================ 0/9 local data check ================
"%PY%" _data_sync.py --check
if errorlevel 1 echo [warn] some local data missing - run _data_sync.py when online

echo ================ 1/9 rules + wizard selftest ================
"%PY%" dnd55e_character_builder.py --selftest
if errorlevel 1 goto fail

echo.
echo ================ 2/9 full flow (18 sections) ================
"%PY%" _flowtest.py
if errorlevel 1 goto fail

echo.
echo ================ 3/9 per-level number check (vs SRD 5.2) ================
"%PY%" _resourcecheck.py
if errorlevel 1 goto fail

echo.
echo ================ 4/9 layout audit ================
"%PY%" _layoutcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 5/9 text audit ================
"%PY%" _textcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 6/9 hint clipping check ================
"%PY%" _hintcheck.py
if errorlevel 1 goto fail

echo.
echo ================ 7/9 summon stat block check ================
"%PY%" _summoncheck.py
if errorlevel 1 goto fail

echo.
echo ================ 8/9 module dependency check ================
"%PY%" _namecheck.py
if errorlevel 1 goto fail

echo.
echo ================ 9/9 done ================
echo ALL CHECKS PASSED
if not defined DND_NO_PAUSE pause
exit /b 0

:fail
echo.
echo CHECK FAILED - see output above
if not defined DND_NO_PAUSE pause
exit /b 1
