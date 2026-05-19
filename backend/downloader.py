import os
import subprocess
import uuid
import re
import json
import time

# ─── Kick Direct Downloader ──────────────────────────────────────────────
# Kicklet gibi siteler nasıl yapıyor?
# 1. Kick'in internal API'sini kullanarak m3u8 URL'yi direkt alıyorlar
# 2. FFmpeg ile -c copy yaparak indiriyorlar (re-encode yok = çok hızlı)
# 3. Cloudflare'e hiç takılmıyorlar çünkü web sayfasını scrape etmiyorlar

def _is_kick_url(url: str) -> bool:
    """URL'nin Kick VOD/video linki olup olmadığını kontrol et"""
    return "kick.com" in url.lower()


def _parse_kick_url(url: str) -> dict:
    """
    Kick URL'sinden video bilgilerini parse et.
    Desteklenen formatlar:
      - https://kick.com/video/VIDEO_UUID
      - https://kick.com/CHANNEL/video/VIDEO_UUID  
      - https://kick.com/CHANNEL?video=VIDEO_UUID
      - https://kick.com/CHANNEL/videos (son yayın)
      - https://kick.com/CHANNEL (son VOD)
    """
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    query_params = urllib.parse.parse_qs(parsed.query)
    
    result = {"channel": None, "video_uuid": None}
    
    # Format: /video/UUID
    if len(path_parts) >= 2 and path_parts[0] == "video":
        result["video_uuid"] = path_parts[1]
        return result
    
    # Format: /CHANNEL/video/UUID
    if len(path_parts) >= 3 and path_parts[1] == "video":
        result["channel"] = path_parts[0]
        result["video_uuid"] = path_parts[2]
        return result
    
    # Format: /CHANNEL?video=UUID
    if len(path_parts) >= 1 and "video" in query_params:
        result["channel"] = path_parts[0]
        result["video_uuid"] = query_params["video"][0]
        return result
    
    # Format: /CHANNEL/videos veya /CHANNEL (kanal sayfası - son VOD'u al)
    if len(path_parts) >= 1:
        result["channel"] = path_parts[0]
        return result
    
    return result


def _get_kick_m3u8_url(url: str) -> dict:
    """
    Kick API'sini kullanarak video bilgilerini ve m3u8 URL'yi al.
    Kicklet'in yaptığı şeyin aynısı - direkt API çağrısı.
    Returns: {"m3u8_url": str, "title": str, "duration": int, "thumbnail": str}
    """
    import urllib.request
    import urllib.error
    
    parsed = _parse_kick_url(url)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://kick.com/",
    }
    
    # Eğer direkt video UUID varsa, video endpoint'ini kullan
    if parsed.get("video_uuid"):
        video_uuid = parsed["video_uuid"]
        api_urls = [
            f"https://kick.com/api/v1/video/{video_uuid}",
            f"https://kick.com/api/v2/video/{video_uuid}",
        ]
        
        for api_url in api_urls:
            try:
                print(f"[Kick Direct] API deneniyor: {api_url}")
                req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    
                    # API yanıt yapısını parse et
                    source = None
                    title = "Kick VOD"
                    duration = 0
                    thumbnail = None
                    
                    # Direkt video objesi
                    if isinstance(data, dict):
                        source = data.get("source") or data.get("playback_url") or data.get("url")
                        title = data.get("session_title") or data.get("title") or title
                        
                        # Livestream objesi içinde olabilir
                        if not source and "livestream" in data:
                            ls = data["livestream"]
                            source = ls.get("source") or ls.get("playback_url")
                            title = ls.get("session_title") or title
                        
                        # Video objesi içinde olabilir
                        if not source and "video" in data:
                            vid = data["video"]
                            source = vid.get("source") or vid.get("playback_url")
                        
                        duration = data.get("duration") or 0
                        thumbnail = data.get("thumbnail") or data.get("poster")
                    
                    if source:
                        print(f"[Kick Direct] ✅ m3u8 bulundu: {source[:80]}...")
                        return {
                            "m3u8_url": source,
                            "title": title,
                            "duration": duration,
                            "thumbnail": thumbnail,
                        }
                    else:
                        print(f"[Kick Direct] ⚠️ API yanıt verdi ama source yok: {json.dumps(data)[:200]}")
                        
            except urllib.error.HTTPError as e:
                print(f"[Kick Direct] HTTP {e.code} hatası: {api_url}")
                continue
            except Exception as e:
                print(f"[Kick Direct] Hata: {e}")
                continue
    
    # Eğer kanal slug'ı varsa, kanalın videolarını listele
    if parsed.get("channel"):
        channel = parsed["channel"]
        api_urls = [
            f"https://kick.com/api/v2/channels/{channel}/videos",
            f"https://kick.com/api/v1/channels/{channel}/videos",
        ]
        
        for api_url in api_urls:
            try:
                print(f"[Kick Direct] Kanal videoları deneniyor: {api_url}")
                req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    
                    # Yanıt bir liste veya data.data listesi olabilir
                    videos = data if isinstance(data, list) else data.get("data", data.get("videos", []))
                    
                    if isinstance(videos, list) and len(videos) > 0:
                        video = videos[0]  # En son VOD
                        source = video.get("source") or video.get("playback_url")
                        title = video.get("session_title") or video.get("title") or "Kick VOD"
                        
                        # İç içe livestream objesi olabilir
                        if not source and "livestream" in video:
                            ls = video["livestream"]
                            source = ls.get("source") or ls.get("playback_url")
                            title = ls.get("session_title") or title
                        
                        if source:
                            print(f"[Kick Direct] ✅ Kanal VOD m3u8 bulundu: {source[:80]}...")
                            return {
                                "m3u8_url": source,
                                "title": title,
                                "duration": video.get("duration", 0),
                                "thumbnail": video.get("thumbnail"),
                            }
                    
                    print(f"[Kick Direct] ⚠️ Kanal API yanıtı: {json.dumps(data)[:300]}")
                    
            except urllib.error.HTTPError as e:
                print(f"[Kick Direct] HTTP {e.code}: {api_url}")
                continue
            except Exception as e:
                print(f"[Kick Direct] Hata: {e}")
                continue
    
    return None


def _download_kick_direct(m3u8_url: str, output_path: str, quality: str = "1080"):
    """
    FFmpeg ile m3u8'den direkt indirme (-c copy = re-encode yok = HIZLI).
    Kicklet'in kullandığı yöntemin aynısı.
    """
    cmd = [
        "ffmpeg",
        "-y",                    # Üzerine yaz
        "-i", m3u8_url,          # m3u8 kaynak
        "-c", "copy",            # RE-ENCODE YOK → ÇOK HIZLI
        "-bsf:a", "aac_adtstoasc",  # AAC uyumluluk
        "-movflags", "+faststart",   # Web player uyumluluğu
        "-progress", "pipe:1",       # Progress bilgisi stdout'a
        "-stats_period", "0.5",      # Her 0.5 saniyede güncelle
        output_path,
    ]
    
    print(f"[Kick Direct] FFmpeg başlatılıyor: {' '.join(cmd)}")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace'
    )
    
    return process


def _kick_download_generator(url: str, quality: str, output_dir: str, custom_name: str = None, dl_format: str = "mp4"):
    """
    Kick VOD'u direkt API + FFmpeg ile indir.
    yt-dlp'ye gerek yok, Cloudflare'e takılma yok.
    """
    yield {"status": "starting", "percent": 0, "message": "🔍 Kick API'den video bilgileri alınıyor..."}
    
    video_info = _get_kick_m3u8_url(url)
    
    if not video_info or not video_info.get("m3u8_url"):
        yield {"status": "fallback", "message": "Kick API'den m3u8 alınamadı, yt-dlp'ye geçiliyor..."}
        return
    
    m3u8_url = video_info["m3u8_url"]
    title = video_info.get("title", "Kick VOD")
    
    yield {"status": "downloading", "percent": 1, "message": f"✅ Video bulundu: {title[:50]}"}
    
    # Dosya adı oluştur
    if custom_name:
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', custom_name)
        filename_id = f"dl_{safe_name}"
    else:
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', title[:40])
        filename_id = f"dl_{safe_name}_{uuid.uuid4().hex[:4]}"
    
    output_path = os.path.join(output_dir, f"{filename_id}.{dl_format}")
    
    yield {"status": "downloading", "percent": 2, "message": "⚡ FFmpeg ile hızlı indirme başlatılıyor (re-encode yok)..."}
    
    # FFmpeg ile indir
    process = _download_kick_direct(m3u8_url, output_path, quality)
    
    # FFmpeg progress takibi
    duration_ms = video_info.get("duration", 0)
    # Kick API duration ms cinsinden veriyor, saniyeye çevir
    duration_seconds = duration_ms / 1000.0 if duration_ms else 0.0
    
    time_pattern = re.compile(r'out_time_us=(\d+)')
    size_pattern = re.compile(r'total_size=(\d+)')
    
    last_percent = 2
    current_size = 0
    start_time = time.time()
    last_update_time = start_time
    last_size = 0
    speed_mbps = 0.0
    
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        
        # FFmpeg progress parsing
        time_match = time_pattern.search(line)
        size_match = size_pattern.search(line)
        
        if size_match:
            current_size = int(size_match.group(1))
        
        if time_match:
            current_us = int(time_match.group(1))
            current_seconds = current_us / 1_000_000
            
            if duration_seconds > 0:
                percent = min(98, max(2, (current_seconds / duration_seconds) * 100))
            else:
                # Duration bilinmiyorsa boyut bazlı tahmin
                percent = min(98, last_percent + 0.1)
            
            last_percent = percent
            
            # Boyut formatla
            if current_size > 0:
                if current_size > 1_073_741_824:
                    size_str = f"{current_size / 1_073_741_824:.1f} GB"
                elif current_size > 1_048_576:
                    size_str = f"{current_size / 1_048_576:.1f} MB"
                else:
                    size_str = f"{current_size / 1024:.0f} KB"
            else:
                size_str = "..."
            
            # Gerçek İndirme Hızı (Network Hızı) Hesaplama
            now = time.time()
            elapsed_since_last = now - last_update_time
            if elapsed_since_last >= 0.5 and current_size > last_size:
                bytes_diff = current_size - last_size
                speed_mbps = (bytes_diff / elapsed_since_last) / 1_048_576
                last_update_time = now
                last_size = current_size
            
            speed_str = f"{speed_mbps:.1f} MB/s" if speed_mbps > 0 else "..."
            
            # Kalan süre tahmini (Gerçek saniye cinsinden videonun geri kalanı / indirme hızı)
            eta_str = "..."
            if duration_seconds > 0 and current_seconds > 0:
                total_elapsed_time = now - start_time
                if percent > 0 and percent < 100:
                    estimated_total = total_elapsed_time / (percent / 100.0)
                    remaining_real_seconds = estimated_total - total_elapsed_time
                    if remaining_real_seconds > 0:
                        mins, secs = divmod(int(remaining_real_seconds), 60)
                        eta_str = f"{mins}:{secs:02d}"
            
            yield {
                "status": "downloading",
                "percent": round(percent, 1),
                "size": size_str,
                "speed": speed_str,
                "eta": eta_str,
                "message": f"⚡ İndiriliyor: %{percent:.1f} - Boyut: {size_str} - Hız: {speed_str} - Kalan: {eta_str}"
            }
    
    process.wait()
    
    if process.returncode != 0:
        yield {"status": "fallback", "message": f"FFmpeg hata verdi (kod: {process.returncode}), yt-dlp'ye geçiliyor..."}
        # Başarısız dosyayı temizle
        if os.path.exists(output_path):
            os.remove(output_path)
        return
    
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        yield {
            "status": "completed",
            "percent": 100,
            "filename": os.path.basename(output_path),
            "message": f"✅ İndirme tamamlandı! ({size_mb:.1f} MB) - Kick Direct API ile hızlı indirildi!"
        }
    else:
        yield {"status": "fallback", "message": "İndirilen dosya boş, yt-dlp'ye geçiliyor..."}


# ─── yt-dlp Fallback ─────────────────────────────────────────────────────

def _ytdlp_download_generator(url: str, quality: str, output_dir: str, custom_name: str = None, dl_format: str = "mp4"):
    """
    yt-dlp ile indirme (YouTube, Twitch ve fallback).
    """
    if custom_name:
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', custom_name)
        filename_id = f"dl_{safe_name}"
    else:
        filename_id = f"dl_{uuid.uuid4().hex[:8]}"
        
    output_template = os.path.join(output_dir, f"{filename_id}.%(ext)s")
    
    if dl_format in ["ts", "mpg"]:
        remux = ["--remux-video", dl_format]
        if quality == "720" or quality == "480":
            format_str = f"best[height<={quality}]/bestvideo[height<={quality}]+bestaudio/best"
        else:
            format_str = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
    else:
        remux = []
        if quality == "720" or quality == "480":
            format_str = f"best[height<={quality}][ext=mp4]/bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best"
        else:
            format_str = f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best"
    
    import sys
    yt_dlp_exe = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    
    cmd = [
        yt_dlp_exe,
        "--newline",
        "--force-ipv4",
        "--socket-timeout", "30",
        "--retries", "10",
        "--fragment-retries", "10",
        "--extractor-retries", "10",
        "-f", format_str,
        "-N", "8",
        "--no-playlist",
        "-o", output_template
    ]
    
    if remux:
        cmd.extend(remux)
        
    cmd.append(url)
    
    print(f"[yt-dlp Fallback] İndirme başlatılıyor: {' '.join(cmd)}")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace'
    )
    
    progress_pattern = re.compile(
        r'\[download\]\s+(?P<percent>[0-9.]+)%\s+of\s+(?P<size>[~]?[0-9.]+[a-zA-Z]+)(?:\s+at\s+(?P<speed>[0-9.]+[a-zA-Z]+/s))?(?:\s+ETA\s+(?P<eta>[0-9:]+))?'
    )
    
    yield {"status": "starting", "percent": 0, "message": "yt-dlp ile indirme başlatılıyor..."}
    
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
            
        match = progress_pattern.search(line)
        if match:
            percent_str = match.group('percent')
            size = match.group('size') or "Bilinmiyor"
            speed = match.group('speed') or "Bilinmiyor"
            eta = match.group('eta') or "Bilinmiyor"
            
            try:
                percent = float(percent_str)
            except ValueError:
                percent = 0
                
            yield {
                "status": "downloading",
                "percent": percent,
                "size": size,
                "speed": speed,
                "eta": eta,
                "message": f"İndiriliyor: %{percent} - Hız: {speed} - Kalan: {eta}"
            }
        elif "[download] Destination:" in line:
            yield {"status": "downloading", "percent": 0, "message": "Video bilgileri alındı, indiriliyor..."}
        elif "[Merger]" in line:
            yield {"status": "processing", "percent": 95, "message": "Video ve ses birleştiriliyor..."}

    process.wait()
    
    if process.returncode != 0:
        yield {"status": "error", "message": "İndirme işlemi başarısız oldu (Hata kodu: " + str(process.returncode) + ")"}
        return

    # Dosya adını bul
    downloaded_file = None
    for file in os.listdir(output_dir):
        if file.startswith(filename_id):
            downloaded_file = os.path.join(output_dir, file)
            break
            
    if downloaded_file:
        yield {"status": "completed", "percent": 100, "filename": os.path.basename(downloaded_file), "message": "İndirme tamamlandı!"}
    else:
        yield {"status": "error", "message": "İndirme başarılı ancak dosya bulunamadı."}


# ─── Ana İndirme Fonksiyonu ──────────────────────────────────────────────

def download_media_generator(url: str, quality: str, output_dir: str, custom_name: str = None, format: str = "mp4"):
    """
    Akıllı indirme motoru:
    - Kick URL'leri → Direkt API + FFmpeg (Kicklet yöntemi, çok hızlı)
    - Diğer URL'ler → yt-dlp (YouTube, Twitch vs.)
    - Kick başarısız olursa → yt-dlp'ye otomatik fallback
    """
    # Tarayıcı uyumluluğu (telefon modunda video editörü) için daima MP4 kullan.
    format = "mp4" 
    os.makedirs(output_dir, exist_ok=True)
    
    # Kick URL'si mi kontrol et
    if _is_kick_url(url):
        print(f"[Downloader] 🎯 Kick URL algılandı, direkt API yöntemi deneniyor...")
        
        for update in _kick_download_generator(url, quality, output_dir, custom_name, format):
            # "fallback" status'u gelirse yt-dlp'ye geç
            if update.get("status") == "fallback":
                print(f"[Downloader] ⚠️ Kick direkt indirme başarısız: {update.get('message')}")
                print(f"[Downloader] 🔄 yt-dlp fallback'e geçiliyor...")
                yield {"status": "downloading", "percent": 0, "message": f"⚠️ {update['message']}"}
                
                # yt-dlp ile dene
                for fallback_update in _ytdlp_download_generator(url, quality, output_dir, custom_name, format):
                    yield fallback_update
                return
            
            yield update
    else:
        # Kick değil, direkt yt-dlp kullan
        print(f"[Downloader] 📺 Kick dışı URL, yt-dlp kullanılıyor...")
        for update in _ytdlp_download_generator(url, quality, output_dir, custom_name, format):
            yield update
