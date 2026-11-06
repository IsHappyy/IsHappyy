@echo off
chcp 65001 >nul
title Jig Board Server
cd /d "%~dp0"
set "NODE=node"
if exist "%~dp0node\node.exe" set "NODE=%~dp0node\node.exe"
echo กำลังเปิดเซิร์ฟเวอร์บอร์ดงาน Jig ... (ปิดหน้าต่างนี้ = ปิดเซิร์ฟเวอร์)
"%NODE%" server.mjs
echo.
echo เซิร์ฟเวอร์หยุดทำงาน
pause
