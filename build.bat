@echo off
chcp 65001 >nul 2>&1
echo ==========================================
echo    Video Compressor - Build Script
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

REM Install dependencies
echo [1/4] Installing dependencies...
pip install Pillow windnd pyinstaller -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

REM Check FFmpeg
echo [2/4] Checking FFmpeg...
if not exist "assets\ffmpeg\ffmpeg.exe" (
    echo.
    echo [INFO] FFmpeg not found. Downloading...
    echo Download from: https://www.gyan.dev/ffmpeg/builds/
    echo Extract and copy ffmpeg.exe and ffprobe.exe to assets\ffmpeg\
    echo.

    REM Try auto download
    echo Trying auto download...
    powershell -Command "$ProgressPreference='SilentlyContinue'; $url='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'; $out='ffmpeg_temp.zip'; try { Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing; Expand-Archive -Path $out -DestinationPath 'ffmpeg_temp' -Force; Copy-Item 'ffmpeg_temp\*\bin\ffmpeg.exe' 'assets\ffmpeg\' -Force; Copy-Item 'ffmpeg_temp\*\bin\ffprobe.exe' 'assets\ffmpeg\' -Force; Remove-Item 'ffmpeg_temp' -Recurse -Force; Remove-Item $out -Force; Write-Host 'FFmpeg downloaded!' } catch { Write-Host 'Auto download failed. Please download manually.' }"
)

if not exist "assets\ffmpeg\ffmpeg.exe" (
    echo [WARNING] FFmpeg still not found.
    echo The packaged EXE will rely on FFmpeg in system PATH.
    echo.
)

REM Prepare icon
echo [3/4] Preparing resources...
if not exist "assets\icon.ico" (
    echo [INFO] Icon file not found, using default icon.
)

REM Build
echo [4/4] Building EXE...
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo.
echo ==========================================
echo    Build complete!
echo    Output: dist\VideoCompressor.exe
echo ==========================================
echo.
pause
