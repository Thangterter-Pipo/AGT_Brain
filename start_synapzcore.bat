@echo off
title SynapzCore Dashboard
cd /d E:\AGT_Brain\scripts
echo ============================================
echo   Khoi dong SynapzCore Dashboard...
echo   Mo trinh duyet: http://localhost:8899
echo ============================================
set PYTHONHOME=
set PYTHONPATH=
python dashboard_server.py
echo.
echo Server da dung. Bam phim bat ky de dong.
pause >nul
