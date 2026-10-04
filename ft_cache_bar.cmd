@echo off
rem ============================================================
rem  FreeToken Cache Bar — 启动常驻浮动小窗
rem
rem  说明：使用 FreeToken 自带的 Python venv（自带 tkinter）。
rem  配置保存于：%USERPROFILE%\.freetoken\cache-presets.json
rem ============================================================

setlocal
set "FT_PY=C:\Users\Fang\AppData\Local\FreeToken\venv\Scripts\pythonw.exe"
set "FT_BAR=C:\Users\Fang\.freetoken\cache-bar\ft_cache_bar.pyw"

if not exist "%FT_PY%" (
  echo [FT Cache Bar] 找不到 Python：%FT_PY%
  pause
  exit /b 1
)
if not exist "%FT_BAR%" (
  echo [FT Cache Bar] 找不到脚本：%FT_BAR%
  pause
  exit /b 1
)

"%FT_PY%" "%FT_BAR%" %*
