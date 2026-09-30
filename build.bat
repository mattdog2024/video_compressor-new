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
echo [1/5] Installing dependencies...
pip install Pillow windnd pyinstaller -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

REM Check FFmpeg
echo [2/5] Checking FFmpeg...
if not exist "assets\ffmpeg\ffmpeg.exe" (
    echo.
    echo [INFO] FFmpeg not found. Downloading...
    echo Downloading FFmpeg 7.1.1 compatible with older NVIDIA drivers.
    echo Extract and copy ffmpeg.exe and ffprobe.exe to assets\ffmpeg\
    echo.

    REM Try auto download
    echo Trying auto download...
    powershell -Command "$ProgressPreference='SilentlyContinue'; $url='https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-essentials_build.zip'; $out='ffmpeg_temp.zip'; try { Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing; Expand-Archive -Path $out -DestinationPath 'ffmpeg_temp' -Force; Copy-Item 'ffmpeg_temp\*\bin\ffmpeg.exe' 'assets\ffmpeg\' -Force; Copy-Item 'ffmpeg_temp\*\bin\ffprobe.exe' 'assets\ffmpeg\' -Force; Remove-Item 'ffmpeg_temp' -Recurse -Force; Remove-Item $out -Force; Write-Host 'FFmpeg downloaded!' } catch { Write-Host 'Auto download failed. Please download manually.' }"
)

if not exist "assets\ffmpeg\ffmpeg.exe" (
    echo [WARNING] FFmpeg still not found.
    echo The packaged EXE will rely on FFmpeg in system PATH.
    echo.
)

REM Check HandBrakeCLI, used for native bitmap subtitle burn-in.
echo [3/5] Checking native bitmap subtitle renderer...
if not exist "assets\handbrake\HandBrakeCLI.exe" (
    echo [INFO] HandBrakeCLI not found. Downloading...
    powershell -Command "$ProgressPreference='SilentlyContinue'; $url='https://github.com/HandBrake/HandBrake/releases/download/1.11.2/HandBrakeCLI-1.11.2-win-x86_64.zip'; $out='handbrake_temp.zip'; try { Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing; Expand-Archive -Path $out -DestinationPath 'handbrake_temp' -Force; New-Item -ItemType Directory -Path 'assets\handbrake' -Force | Out-Null; Copy-Item 'handbrake_temp\HandBrakeCLI.exe' 'assets\handbrake\' -Force; Copy-Item 'handbrake_temp\doc\COPYING' 'assets\handbrake\' -Force; Copy-Item 'handbrake_temp\doc\LICENSE' 'assets\handbrake\' -Force; Remove-Item 'handbrake_temp' -Recurse -Force; Remove-Item $out -Force; Write-Host 'HandBrakeCLI downloaded!' } catch { Write-Host 'Auto download failed. PGS/DVB/VobSub subtitles will not be available in this build.' }"
)

REM Prepare icon
echo [4/5] Preparing resources...
if not exist "assets\icon.ico" (
    echo [INFO] Icon file not found, using default icon.
)

REM Build
echo [5/5] Building EXE...
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
