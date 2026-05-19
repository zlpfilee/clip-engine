@echo off
chcp 65001 >nul 2>&1
title ClipEngine - İçerik Otomasyon Merkezi
color 0A

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║        🎬 ClipEngine Başlatılıyor...         ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: Proje dizinine geç
cd /d "%~dp0"

:: ─── Python Kontrolü ───
echo [1/5] Python kontrol ediliyor...
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadı! Python 3.10+ yükleyin.
    echo        https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do echo       Python %%v bulundu ✓

:: ─── FFmpeg Kontrolü ───
echo [2/5] FFmpeg kontrol ediliyor...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [HATA] FFmpeg bulunamadı! FFmpeg yükleyin ve PATH'e ekleyin.
    echo        https://ffmpeg.org/download.html
    pause
    exit /b 1
)
echo       FFmpeg bulundu ✓

:: ─── Virtual Environment ───
echo [3/5] Sanal ortam kontrol ediliyor...
if not exist "venv\Scripts\activate.bat" (
    echo       Sanal ortam oluşturuluyor...
    python -m venv venv
    if errorlevel 1 (
        echo [HATA] Sanal ortam oluşturulamadı!
        pause
        exit /b 1
    )
    echo       Sanal ortam oluşturuldu ✓
) else (
    echo       Sanal ortam mevcut ✓
)

:: Sanal ortamı aktif et
call venv\Scripts\activate.bat

:: ─── Bağımlılıklar ───
echo [4/5] Bağımlılıklar kontrol ediliyor...

:: requirements.txt'nin hash'ini kontrol et (değişmişse yeniden yükle)
set "HASH_FILE=venv\.req_hash"
set "NEED_INSTALL=0"

if not exist "%HASH_FILE%" (
    set "NEED_INSTALL=1"
) else (
    certutil -hashfile backend\requirements.txt MD5 2>nul | findstr /v ":" > "%TEMP%\req_hash_new.tmp"
    fc /b "%HASH_FILE%" "%TEMP%\req_hash_new.tmp" >nul 2>&1
    if errorlevel 1 set "NEED_INSTALL=1"
    del "%TEMP%\req_hash_new.tmp" 2>nul
)

if "%NEED_INSTALL%"=="1" (
    echo       Paketler yükleniyor ^(ilk seferde biraz sürebilir^)...
    python -m pip install --upgrade pip setuptools wheel --quiet
    pip install -r backend\requirements.txt --quiet
    certutil -hashfile backend\requirements.txt MD5 2>nul ^| findstr /v ":" > "%HASH_FILE%"
    echo       Paketler yüklendi ✓
) else (
    echo       Tüm paketler güncel ✓
)

:: ─── Gerekli Dizinleri Oluştur ───
if not exist "media\sources" mkdir "media\sources"
if not exist "media\clips" mkdir "media\clips"
if not exist "media\exports" mkdir "media\exports"
if not exist "media\watermarks" mkdir "media\watermarks"
if not exist "data" mkdir "data"

:: ─── Sunucuyu Başlat ───
echo [5/5] ClipEngine başlatılıyor...
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║  Dashboard:  http://localhost:8899           ║
echo  ║  API Docs:   http://localhost:8899/docs      ║
echo  ║                                              ║
echo  ║  Kapatmak icin: Ctrl+C veya pencereyi kapat  ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: 2 saniye sonra tarayıcıyı aç
start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8899"

:: Sunucuyu başlat
cd backend
python main.py

:: Sunucu kapandığında
echo.
echo  ClipEngine kapatıldı.
pause