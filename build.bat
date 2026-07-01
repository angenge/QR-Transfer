@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   QR Transfer - Build Script
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "UPX_DIR=%SCRIPT_DIR%upx.exe"

REM Check dependencies
echo [1/4] Checking dependencies...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not found. Install with: pip install pyinstaller
    exit /b 1
)
echo   PyInstaller: OK

REM Clean old builds
echo.
echo [2/4] Cleaning old build artifacts...
if exist "%SCRIPT_DIR%build" rmdir /s /q "%SCRIPT_DIR%build"
if exist "%SCRIPT_DIR%dist" rmdir /s /q "%SCRIPT_DIR%dist"
echo   Done.

REM Build Sender
echo.
echo [3/4] Building QR_Sender.exe...
pyinstaller --noconfirm --onefile --windowed ^
    --name "QR_Sender" ^
    --clean ^
    "%SCRIPT_DIR%qr_sender_gui.py"
if errorlevel 1 (
    echo ERROR: Failed to build QR_Sender
    exit /b 1
)
echo   QR_Sender.exe built successfully.

REM Build Receiver
echo.
echo [4/4] Building QR_Receiver.exe...
pyinstaller --noconfirm --onefile --windowed ^
    --name "QR_Receiver" ^
    --clean ^
    "%SCRIPT_DIR%qr_receiver.py"
if errorlevel 1 (
    echo ERROR: Failed to build QR_Receiver
    exit /b 1
)
echo   QR_Receiver.exe built successfully.

REM UPX Compression (optional)
if exist "%UPX_DIR%" (
    echo.
    echo [*] Compressing with UPX...
    "%UPX_DIR%" --best --lzma "%SCRIPT_DIR%dist\QR_Sender.exe" 2>nul
    "%UPX_DIR%" --best --lzma "%SCRIPT_DIR%dist\QR_Receiver.exe" 2>nul
    echo   UPX compression done.
)

REM Clean temp build files
if exist "%SCRIPT_DIR%build" rmdir /s /q "%SCRIPT_DIR%build"
if exist "%SCRIPT_DIR%QR_Sender.spec" del "%SCRIPT_DIR%QR_Sender.spec"
if exist "%SCRIPT_DIR%QR_Receiver.spec" del "%SCRIPT_DIR%QR_Receiver.spec"

echo.
echo ========================================
echo   Build Complete!
echo   Output: dist\QR_Sender.exe
echo           dist\QR_Receiver.exe
echo ========================================
pause
