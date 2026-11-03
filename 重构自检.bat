@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  dnd5r 重构自检（单测 / 分层 / 插件 / 黄金 / 布局 / 布局·英文 / 文案）
echo ============================================
"C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe" tools\selfcheck.py
set CODE=%ERRORLEVEL%
echo.
if %CODE%==0 (
  echo 自检通过。
) else (
  echo 自检失败，退出码 %CODE%。
)
if not defined DND_NO_PAUSE pause
exit /b %CODE%
