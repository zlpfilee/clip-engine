"""
ClipEngine Launcher - Tek tıkla kurulum, güncelleme ve çalıştırma
Bu dosya PyInstaller ile .exe'ye dönüştürülecek.
Arkadaşlar sadece bu exe'yi çalıştırır.
"""

import os
import sys
import time
import json
import shutil
import zipfile
import subprocess
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import urllib.request
import urllib.error
import ssl

# ─── Ayarlar ─────────────────────────────────────────────────────────────
GITHUB_REPO = "zlpfilee/clip-engine"
GITHUB_BRANCH = "main"
GITHUB_TOKEN = ""  # Token olmadan public repo, token ile private repo çalışır

APP_NAME = "ClipEngine"
INSTALL_DIR = Path(os.environ["USERPROFILE"]) / "ClipEngine"
PYTHON_DIR = INSTALL_DIR / "_python"
FFMPEG_DIR = INSTALL_DIR / "_ffmpeg"
APP_DIR = INSTALL_DIR / "app"
CONFIG_FILE = INSTALL_DIR / "launcher_config.json"
LOG_FILE = INSTALL_DIR / "ClipEngine_debug.log"

PYTHON_VERSION = "3.11.9"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# SSL context (bazı Windows'larda sertifika sorunu olabiliyor)
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def log(msg):
    """Debug log dosyasina yaz"""
    try:
        os.makedirs(INSTALL_DIR, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}\n"
        with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write(line)
        print(line.strip())
    except Exception:
        pass


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(data):
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


class ClipEngineLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🎬 ClipEngine")
        self.root.geometry("520x400")
        self.root.resizable(False, False)
        self.root.configure(bg="#0a0a0a")
        
        # İkon ve pencere ayarları
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))
        
        self.server_process = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        self._center_window()
        self._build_ui()
        
        # Kurulumu arka planda başlat
        self.thread = threading.Thread(target=self._setup_and_launch, daemon=True)
        self.thread.start()
    
    def _center_window(self):
        self.root.update_idletasks()
        w = 520
        h = 400
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
    
    def _on_closing(self):
        self._set_status("Kapatılıyor...", "Lütfen bekleyin...")
        self.root.update()
        if hasattr(self, 'server_process') and self.server_process:
            try:
                self.server_process.kill()
            except Exception:
                pass
        self.root.destroy()
        
    def _build_ui(self):
        # Ana frame
        main = tk.Frame(self.root, bg="#0a0a0a")
        main.pack(fill="both", expand=True, padx=30, pady=20)
        
        # Başlık
        tk.Label(main, text="🎬", font=("Segoe UI Emoji", 40), bg="#0a0a0a", fg="white").pack(pady=(10, 0))
        tk.Label(main, text="ClipEngine", font=("Segoe UI", 24, "bold"), bg="#0a0a0a", fg="white").pack()
        tk.Label(main, text="İçerik Otomasyon Merkezi", font=("Segoe UI", 10), bg="#0a0a0a", fg="#888").pack()
        
        # Spacer
        tk.Frame(main, bg="#0a0a0a", height=20).pack()
        
        # Durum mesajı
        self.status_var = tk.StringVar(value="Başlatılıyor...")
        self.status_label = tk.Label(main, textvariable=self.status_var, font=("Segoe UI", 11), bg="#0a0a0a", fg="#4ade80", wraplength=440)
        self.status_label.pack(pady=(0, 8))
        
        # Alt durum
        self.substatus_var = tk.StringVar(value="")
        tk.Label(main, textvariable=self.substatus_var, font=("Segoe UI", 9), bg="#0a0a0a", fg="#666", wraplength=440).pack(pady=(0, 10))
        
        # Progress bar
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("green.Horizontal.TProgressbar", troughcolor="#1a1a1a", background="#4ade80", bordercolor="#0a0a0a", lightcolor="#4ade80", darkcolor="#4ade80")
        
        self.progress = ttk.Progressbar(main, style="green.Horizontal.TProgressbar", length=440, mode="determinate")
        self.progress.pack(pady=(0, 10))
        
        # Adımlar listesi
        self.steps_frame = tk.Frame(main, bg="#0a0a0a")
        self.steps_frame.pack(fill="x", pady=(5, 0))
        
        self.step_labels = {}
        steps = ["Python", "FFmpeg", "ClipEngine Kodu", "Paketler", "Sunucu"]
        for step in steps:
            frame = tk.Frame(self.steps_frame, bg="#0a0a0a")
            frame.pack(fill="x", pady=1)
            icon = tk.Label(frame, text="⏳", font=("Segoe UI", 9), bg="#0a0a0a", fg="#555", width=3)
            icon.pack(side="left")
            label = tk.Label(frame, text=step, font=("Segoe UI", 9), bg="#0a0a0a", fg="#555", anchor="w")
            label.pack(side="left")
            self.step_labels[step] = (icon, label)
    
    def _set_step(self, name, state="active"):
        """Adım durumunu güncelle: pending, active, done, error"""
        if name not in self.step_labels:
            return
        icon, label = self.step_labels[name]
        states = {
            "pending": ("⏳", "#555", "#555"),
            "active": ("🔄", "#4ade80", "#ccc"),
            "done": ("✅", "#4ade80", "#4ade80"),
            "error": ("❌", "#ef4444", "#ef4444"),
            "skip": ("⏭️", "#888", "#888"),
        }
        i, ic, lc = states.get(state, states["pending"])
        self.root.after(0, lambda: (icon.config(text=i, fg=ic), label.config(fg=lc)))
    
    def _set_status(self, msg, sub=""):
        self.root.after(0, lambda: (self.status_var.set(msg), self.substatus_var.set(sub)))
    
    def _set_progress(self, value):
        self.root.after(0, lambda: self.progress.configure(value=value))
    
    def _download(self, url, dest, label=""):
        """Dosya indir (progress gösteren)"""
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        
        req = urllib.request.Request(url, headers=headers)
        
        try:
            response = urllib.request.urlopen(req, context=ssl_ctx)
        except urllib.error.HTTPError as e:
            # GitHub API redirect durumu
            if e.code == 302:
                response = urllib.request.urlopen(e.headers["Location"], context=ssl_ctx)
            else:
                raise
        
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        start_time = time.time()
        
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            while True:
                chunk = response.read(8192 * 4)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                
                if total > 0:
                    elapsed = time.time() - start_time
                    speed = (downloaded / 1024 / 1024) / elapsed if elapsed > 0 else 0
                    pct = int(downloaded / total * 100)
                    mb_done = downloaded / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    
                    self._set_status(
                        f"{label} indiriliyor... ({pct}%)", 
                        f"{mb_done:.1f} MB / {mb_total:.1f} MB • Hız: {speed:.1f} MB/s"
                    )
    
    def _github_api(self, endpoint):
        """GitHub API çağrısı yap"""
        url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
        headers = {"Accept": "application/vnd.github.v3.raw", "User-Agent": "ClipEngine-Launcher"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        
        req = urllib.request.Request(url, headers=headers)
        try:
            response = urllib.request.urlopen(req, context=ssl_ctx, timeout=10)
            return response.read().decode("utf-8").strip()
        except Exception:
            return None
    
    def _github_download_zip(self, dest):
        """GitHub'dan repo ZIP'ini indir"""
        url = f"https://api.github.com/repos/{GITHUB_REPO}/zipball/{GITHUB_BRANCH}"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ClipEngine-Launcher"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        
        req = urllib.request.Request(url, headers=headers)
        
        try:
            response = urllib.request.urlopen(req, context=ssl_ctx)
        except urllib.error.HTTPError as e:
            if e.code == 302 or (hasattr(e, 'headers') and e.headers.get("Location")):
                loc = e.headers.get("Location", "")
                if loc:
                    response = urllib.request.urlopen(loc, context=ssl_ctx)
                else:
                    raise
            else:
                raise
        
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        start_time = time.time()
        
        with open(dest, "wb") as f:
            while True:
                chunk = response.read(8192 * 4)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                
                if total > 0:
                    elapsed = time.time() - start_time
                    speed = (downloaded / 1024 / 1024) / elapsed if elapsed > 0 else 0
                    pct = int(downloaded / total * 100)
                    mb_done = downloaded / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    
                    self._set_status(
                        f"ClipEngine indiriliyor... ({pct}%)", 
                        f"{mb_done:.1f} MB / {mb_total:.1f} MB • Hız: {speed:.1f} MB/s"
                    )
                else:
                    elapsed = time.time() - start_time
                    speed = (downloaded / 1024 / 1024) / elapsed if elapsed > 0 else 0
                    mb_done = downloaded / 1024 / 1024
                    self._set_status("ClipEngine indiriliyor...", f"{mb_done:.1f} MB indirildi • Hız: {speed:.1f} MB/s")
    
    def _setup_python(self):
        """Portable Python kur"""
        self._set_step("Python", "active")
        
        # Zaten kuruluysa geç
        python_exe = PYTHON_DIR / "python.exe"
        if python_exe.exists():
            self._set_step("Python", "done")
            return str(python_exe)
        
        # Sistem Python kontrol
        try:
            result = subprocess.run(["python", "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self._set_step("Python", "done")
                return "python"
        except Exception:
            pass
        
        # İndir
        self._set_status("Portable Python indiriliyor...", "İlk kurulum - sadece bir kez (yaklaşık 30 MB)")
        self._set_progress(5)
        
        zip_path = str(INSTALL_DIR / "_python_temp.zip")
        self._download(PYTHON_URL, zip_path, "Python")
        
        # Çıkar
        self._set_status("Python kuruluyor...")
        os.makedirs(PYTHON_DIR, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(PYTHON_DIR)
        os.remove(zip_path)
        
        # _pth dosyasını düzenle (pip için gerekli)
        for pth_file in PYTHON_DIR.glob("python*._pth"):
            content = pth_file.read_text()
            content = content.replace("#import site", "import site")
            pth_file.write_text(content)
        
        # pip kur
        self._set_status("pip kuruluyor...")
        getpip = str(INSTALL_DIR / "_get_pip.py")
        self._download("https://bootstrap.pypa.io/get-pip.py", getpip, "pip")
        subprocess.run([str(python_exe), getpip, "--quiet"], capture_output=True)
        if os.path.exists(getpip):
            os.remove(getpip)
        
        self._set_step("Python", "done")
        self._set_progress(20)
        return str(python_exe)
    
    def _setup_ffmpeg(self):
        """Portable FFmpeg kur"""
        self._set_step("FFmpeg", "active")
        
        ffmpeg_exe = FFMPEG_DIR / "ffmpeg.exe"
        
        # Zaten kuruluysa
        if ffmpeg_exe.exists():
            self._set_step("FFmpeg", "done")
            return
        
        # Sistemde var mı
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self._set_step("FFmpeg", "done")
                return
        except Exception:
            pass
        
        # İndir
        self._set_status("FFmpeg indiriliyor...", "İlk kurulum - sadece bir kez (yaklaşık 140 MB)")
        self._set_progress(25)
        
        zip_path = str(INSTALL_DIR / "_ffmpeg_temp.zip")
        self._download(FFMPEG_URL, zip_path, "FFmpeg")
        
        # Çıkar (sadece bin/ klasöründeki exe'leri al)
        self._set_status("FFmpeg kuruluyor...")
        os.makedirs(FFMPEG_DIR, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as z:
            for entry in z.namelist():
                if '/bin/' in entry and entry.endswith('.exe'):
                    filename = os.path.basename(entry)
                    with z.open(entry) as src, open(FFMPEG_DIR / filename, 'wb') as dst:
                        dst.write(src.read())
        
        os.remove(zip_path)
        
        if not ffmpeg_exe.exists():
            self._set_step("FFmpeg", "error")
            raise RuntimeError("FFmpeg kurulumu başarısız!")
        
        self._set_step("FFmpeg", "done")
        self._set_progress(45)
    
    def _setup_code(self):
        """GitHub'dan kodu indir/guncelle"""
        self._set_step("ClipEngine Kodu", "active")
        self._set_progress(50)
        
        local_version = "0.0.0"
        version_file = APP_DIR / "version.txt"
        if version_file.exists():
            local_version = version_file.read_text().strip()
        log(f"Lokal versiyon: {local_version}")
        
        # Uzak versiyon kontrol
        self._set_status("Güncelleme kontrol ediliyor...")
        remote_version = self._github_api(f"contents/version.txt?ref={GITHUB_BRANCH}")
        log(f"Uzak versiyon: {remote_version}")
        
        need_update = False
        if not (APP_DIR / "backend" / "main.py").exists():
            need_update = True
            log("main.py bulunamadi -> ilk kurulum")
            self._set_status("İlk kurulum - ClipEngine indiriliyor...")
        elif remote_version and remote_version != local_version:
            need_update = True
            log(f"Versiyon farki: {local_version} -> {remote_version}")
            self._set_status(f"Güncelleme bulundu: v{local_version} → v{remote_version}")
        else:
            log("Versiyon guncel, guncelleme gerekmiyor.")
            self._set_status("ClipEngine güncel ✓")
        
        if need_update:
            zip_path = str(INSTALL_DIR / "_code_temp.zip")
            
            try:
                log("GitHub ZIP indiriliyor...")
                self._github_download_zip(zip_path)
                log(f"ZIP indirildi: {os.path.getsize(zip_path)} bytes")
            except Exception as e:
                log(f"ZIP indirme hatasi: {e}")
                if (APP_DIR / "backend" / "main.py").exists():
                    self._set_status("Güncelleme indirilemedi, mevcut sürüm kullanılıyor.")
                    self._set_step("ClipEngine Kodu", "done")
                    return True
                else:
                    raise RuntimeError(f"Kod indirilemedi: {e}")
            
            # Kullanıcı dosyalarını yedekle
            self._set_status("Dosyalar güncelleniyor...")
            backups = {}
            for folder in ["media", "data"]:
                src = APP_DIR / folder
                if src.exists():
                    dst = INSTALL_DIR / f"_backup_{folder}"
                    if dst.exists():
                        shutil.rmtree(dst)
                    log(f"Yedekleniyor: {folder}")
                    shutil.move(str(src), str(dst))
                    backups[folder] = dst
            
            config_backup = None
            if (APP_DIR / "config.json").exists():
                config_backup = INSTALL_DIR / "_backup_config.json"
                shutil.copy2(APP_DIR / "config.json", config_backup)
            
            # Eski kodu sil
            if APP_DIR.exists():
                log("Eski kod siliniyor...")
                try:
                    shutil.rmtree(APP_DIR)
                    log("Eski kod silindi.")
                except Exception as e:
                    log(f"Eski kod silinirken hata: {e}")
                    # Dosya dosya silmeyi dene
                    import stat
                    for root, dirs, files in os.walk(APP_DIR, topdown=False):
                        for name in files:
                            fp = os.path.join(root, name)
                            try:
                                os.chmod(fp, stat.S_IWRITE)
                                os.remove(fp)
                            except Exception:
                                log(f"  Silinemedi: {fp}")
                        for name in dirs:
                            dp = os.path.join(root, name)
                            try:
                                os.rmdir(dp)
                            except Exception:
                                pass
                    try:
                        os.rmdir(str(APP_DIR))
                    except Exception:
                        pass
            
            # ZIP'i çıkar
            log("ZIP cikartiliyor...")
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(INSTALL_DIR / "_code_extract")
            
            # GitHub zip içindeki ilk klasörü app'e taşı
            extract_dir = INSTALL_DIR / "_code_extract"
            for item in extract_dir.iterdir():
                if item.is_dir():
                    shutil.move(str(item), str(APP_DIR))
                    log(f"Kod klasoru tasindi: {item.name} -> app")
                    break
            
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            os.remove(zip_path)
            
            # Yedekleri geri yükle
            for folder, backup_path in backups.items():
                dst = APP_DIR / folder
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.move(str(backup_path), str(dst))
                log(f"Yedek geri yuklendi: {folder}")
            
            if config_backup and config_backup.exists():
                shutil.copy2(config_backup, APP_DIR / "config.json")
                os.remove(config_backup)
            
            # Paket hash'ini sil ki paketler tekrar kurulsun
            hash_file = INSTALL_DIR / "_req_hash.txt"
            if hash_file.exists():
                hash_file.unlink()
                log("Paket hash'i silindi, paketler yeniden kurulacak.")
            
            # Dogrulama: version.txt kontrol
            new_vf = APP_DIR / "version.txt"
            if new_vf.exists():
                new_ver = new_vf.read_text().strip()
                log(f"Guncelleme sonrasi versiyon: {new_ver}")
                self._set_status(f"ClipEngine v{new_ver} güncellendi! ✓")
            else:
                log("UYARI: Guncelleme sonrasi version.txt bulunamadi!")
            
            self._set_step("ClipEngine Kodu", "done")
            self._set_progress(60)
            return True  # packages need reinstall
        
        self._set_step("ClipEngine Kodu", "done")
        self._set_progress(60)
        return False
    
    def _setup_packages(self, python_exe, force=False):
        """Pip paketlerini kur"""
        self._set_step("Paketler", "active")
        self._set_progress(65)
        
        req_file = APP_DIR / "backend" / "requirements.txt"
        hash_file = INSTALL_DIR / "_req_hash.txt"
        
        if not req_file.exists():
            self._set_step("Paketler", "error")
            raise RuntimeError("requirements.txt bulunamadı!")
        
        # Hash kontrolü
        import hashlib
        current_hash = hashlib.md5(req_file.read_bytes()).hexdigest()
        
        if not force and hash_file.exists():
            saved_hash = hash_file.read_text().strip()
            if saved_hash == current_hash:
                self._set_status("Tüm paketler güncel ✓")
                self._set_step("Paketler", "done")
                self._set_progress(85)
                return
        
        self._set_status("Python paketleri kuruluyor...", "İlk seferde biraz sürebilir")
        
        # pip upgrade
        subprocess.run([python_exe, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "--quiet"], capture_output=True)
        
        # requirements install
        process = subprocess.Popen(
            [python_exe, "-m", "pip", "install", "-r", str(req_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line:
                if "Downloading" in line or "Installing collected" in line or "Processing" in line:
                    short_line = line[:70] + "..." if len(line) > 70 else line
                    self._set_status("Yapay zeka ve sunucu paketleri kuruluyor...", short_line)
        
        process.wait()
        
        if process.returncode != 0:
            self._set_status("Bazı paketler yüklenirken uyarı verdi, devam ediliyor...", "")
        
        # Hash kaydet
        hash_file.write_text(current_hash)
        
        self._set_status("Paketler hazır ✓", "Tüm paketler kuruldu.")
        self._set_step("Paketler", "done")
        self._set_progress(85)
    
    def _launch_server(self, python_exe):
        """FastAPI sunucuyu başlat"""
        self._set_step("Sunucu", "active")
        self._set_progress(90)
        self._set_status("ClipEngine başlatılıyor...")
        
        # Gerekli klasörleri oluştur
        for d in ["media/sources", "media/clips", "media/exports", "media/watermarks", "data"]:
            os.makedirs(APP_DIR / d, exist_ok=True)
        
        # PATH'e FFmpeg ekle
        env = os.environ.copy()
        if (FFMPEG_DIR / "ffmpeg.exe").exists():
            env["PATH"] = str(FFMPEG_DIR) + ";" + env.get("PATH", "")
        
        # Sunucuyu başlat
        server_process = subprocess.Popen(
            [python_exe, "main.py"],
            cwd=str(APP_DIR / "backend"),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        
        # Sunucunun başlamasını bekle
        self._set_status("Sunucu başlatılıyor...")
        import urllib.request
        max_wait = 15
        for i in range(max_wait * 2):
            try:
                urllib.request.urlopen("http://localhost:8899", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
                if server_process.poll() is not None:
                    # Sunucu çöktü
                    output = server_process.stdout.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"Sunucu başlatılamadı:\n{output[-500:]}")
        
        self._set_step("Sunucu", "done")
        self._set_progress(100)
        
        # Tarayıcıyı aç
        webbrowser.open("http://localhost:8899")
        
        # UI'ı güncelle - çalışıyor modu
        self._set_status("🟢 ClipEngine çalışıyor!", "Tarayıcıda http://localhost:8899 açıldı • Kapatmak için bu pencereyi kapatın")
        
        # Pencereyi küçült ama taskbar'da kalsın
        self.root.after(2000, lambda: self.root.iconify())
        
        # Sunucu durmasını bekle
        self.server_process = server_process
        try:
            server_process.wait()
        except KeyboardInterrupt:
            server_process.terminate()
        
        return server_process
    
    def _kill_old_processes(self):
        """Onceki calismadan kalan Python/FFmpeg islemlerini zorla oldur"""
        log("Eski islemler kontrol ediliyor...")
        self._set_status("Eski islemler temizleniyor...")
        
        install_str = str(INSTALL_DIR).lower()
        
        try:
            # WMIC ile ClipEngine dizinindeki python.exe ve ffmpeg.exe'leri bul ve oldur
            for proc_name in ["python.exe", "ffmpeg.exe", "ffprobe.exe"]:
                try:
                    result = subprocess.run(
                        ["wmic", "process", "where", 
                         f"name='{proc_name}'", "get", "ProcessId,ExecutablePath", "/format:csv"],
                        capture_output=True, text=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    for line in result.stdout.strip().split("\n"):
                        line = line.strip()
                        if not line or "ExecutablePath" in line or "Node" in line:
                            continue
                        parts = line.split(",")
                        if len(parts) >= 3:
                            exe_path = parts[1].strip().lower()
                            pid = parts[2].strip()
                            if install_str in exe_path and pid.isdigit():
                                log(f"  Eski islem olduruluyor: PID={pid} Path={exe_path}")
                                subprocess.run(["taskkill", "/F", "/PID", pid],
                                             capture_output=True, timeout=5,
                                             creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception as e:
                    log(f"  WMIC hata ({proc_name}): {e}")
        except Exception as e:
            log(f"Islem temizleme hatasi: {e}")
        
        log("Eski islem temizligi tamamlandi.")
        time.sleep(1)  # Dosya kilitlerinin acilmasi icin kisa bekle
    
    def _setup_and_launch(self):
        """Ana kurulum ve baslat akisi"""
        try:
            # Log dosyasini sifirla
            try:
                os.makedirs(INSTALL_DIR, exist_ok=True)
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.write(f"=== ClipEngine Debug Log ===")
                    f.write(f"\nBaslangic: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"INSTALL_DIR: {INSTALL_DIR}\n")
                    f.write(f"APP_DIR: {APP_DIR}\n\n")
            except Exception:
                pass
            
            # 0. Eski islemleri oldur
            self._kill_old_processes()
            
            # 1. Python
            log("=== ADIM 1: Python ===")
            python_exe = self._setup_python()
            log(f"Python OK: {python_exe}")
            
            # 2. FFmpeg
            log("=== ADIM 2: FFmpeg ===")
            self._setup_ffmpeg()
            log("FFmpeg OK")
            
            # 3. Kodu indir/guncelle
            log("=== ADIM 3: Kod Guncelleme ===")
            code_updated = self._setup_code()
            log(f"Kod guncellendi mi: {code_updated}")
            
            # Guncelleme sonrasi version kontrolu
            vf = APP_DIR / "version.txt"
            if vf.exists():
                log(f"Yuklenen versiyon: {vf.read_text().strip()}")
            
            # 4. Paketleri kur
            log("=== ADIM 4: Paketler ===")
            self._setup_packages(python_exe, force=code_updated)
            log("Paketler OK")
            
            # 5. Sunucuyu baslat
            log("=== ADIM 5: Sunucu ===")
            self._launch_server(python_exe)
            
        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            log(f"KRITIK HATA: {err_msg}")
            self._set_status(f"Hata: {str(e)}", f"Detaylar: {LOG_FILE}")
            self.root.after(0, lambda: messagebox.showerror(
                "ClipEngine Hata", 
                f"Bir hata olustu:\n\n{str(e)}\n\nDetayli log:\n{LOG_FILE}"
            ))
    
    def run(self):
        # Pencere kapatildiginda sunucuyu da kapat
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
    
    def _on_close(self):
        log("Kapatiliyor...")
        if hasattr(self, 'server_process') and self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=3)
            except Exception:
                try:
                    self.server_process.kill()
                except Exception:
                    pass
        self.root.destroy()
        os._exit(0)


def main():
    # Public repo olduğu için token'a gerek yok, direkt başlat
    app = ClipEngineLauncher()
    app.run()


if __name__ == "__main__":
    main()
