@echo off
chcp 65001 >nul
cd /d "%~dp0"
cls
echo  ======================================
echo    Hermes Signal Compass
echo  ======================================
echo   1. US Mode (short / index)
echo   2. A-Share Mode
echo   3. Review (daily notes)
echo   4. Portfolio (watchlist)
echo  ======================================
echo.
choice /c 1234 /n /m "  Select (1/2/3/4): "
if errorlevel 4 python compass.py portfolio & goto :after
if errorlevel 3 python compass.py review & goto :after
if errorlevel 2 python compass.py a & goto :after
python compass.py us
:after
pause