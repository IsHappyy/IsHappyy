@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "NODE=node"
if exist "%~dp0node\node.exe" set "NODE=%~dp0node\node.exe"
echo ปิดเซิร์ฟเวอร์ก่อน แล้วค่อยรันไฟล์นี้
"%NODE%" server.mjs user admin admin
pause
