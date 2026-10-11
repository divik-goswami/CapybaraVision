@echo off
setlocal
echo ====================================================
echo Building Capybara Vision Application and Installer
echo ====================================================

python -m pip install -q pyinstaller

echo [1/2] Building CapybaraVision.exe...
pyinstaller --clean CAPI_Search.spec
if exist "dist\CapybaraVision.exe" (
    copy /Y "dist\CapybaraVision.exe" "CapybaraVision.exe" >nul
    copy /Y "dist\CapybaraVision.exe" "CAPI_Search.exe" >nul
    echo [OK] CapybaraVision.exe ready!
) else (
    echo [ERROR] Failed to build CapybaraVision.exe
    pause
    exit /b 1
)

echo [2/2] Building CapybaraVision_Setup.exe (Installer)...
pyinstaller --clean installer.spec
if exist "dist\CapybaraVision_Setup.exe" (
    copy /Y "dist\CapybaraVision_Setup.exe" "CapybaraVision_Setup.exe" >nul
    echo [OK] CapybaraVision_Setup.exe installer ready!
) else (
    echo [ERROR] Failed to build installer
    pause
    exit /b 1
)

:: Clean temporary build artifacts
if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"

echo ====================================================
echo Build Succeeded!
echo - CapybaraVision.exe (Portable App)
echo - CapybaraVision_Setup.exe (Full Windows Installer)
echo ====================================================
pause
