"""
ClipEngine - FastAPI Backend
Ana sunucu: video işleme, dosya yönetimi ve platform upload API'ları
"""

import os
import sys
import json
import uuid
import shutil
import asyncio
import threading
from pathlib import Path

# Embedded Python (Portable) için bulunduğu dizini sys.path'e ekle
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from datetime import datetime
import re
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from video_processor import (
    get_video_info, cut_clip, crop_to_vertical,
    add_watermark, add_hook_text, generate_subtitles,
    burn_subtitles, full_pipeline, get_video_codec_args,
    _run_ffmpeg, slog
)


BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = BASE_DIR / "media"
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "data" / "clips.json"

app = FastAPI(title="ClipEngine", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/frontend", StaticFiles(directory=str(BASE_DIR / "frontend")), name="frontend")
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


# ─── Job Progress Tracking ────────────────────────────────────────────────

# Global dict: job_id -> { status, progress, step, steps_done, steps_total, error, result }
_jobs = {}
_job_lock = threading.Lock()


def _update_job(job_id: str, **kwargs):
    with _job_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _get_job(job_id: str):
    with _job_lock:
        return dict(_jobs.get(job_id, {}))


def range_requests_response(request: Request, file_path: str, content_type: str):
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")
    
    # Tutarlı ETag ve Last-Modified header'ları — tarayıcının seek desteği için kritik
    stat = os.stat(file_path)
    from email.utils import formatdate
    from hashlib import md5
    etag_base = f"{stat.st_mtime}-{stat.st_size}"
    etag = f'"{md5(etag_base.encode()).hexdigest()}"'
    last_modified = formatdate(stat.st_mtime, usegmt=True)
    
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": content_type,
        "ETag": etag,
        "Last-Modified": last_modified,
        "Cache-Control": "public, max-age=3600",
    }
    
    def file_iterator(file_path, byte1, length, chunk_size=8192*4):
        with open(file_path, "rb") as f:
            f.seek(byte1)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                yield chunk
                remaining -= len(chunk)
    
    if range_header:
        byte1, byte2 = 0, None
        match = re.search(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            groups = match.groups()
            byte1 = int(groups[0])
            if groups[1]:
                byte2 = int(groups[1])
        
        if byte2 is None:
            byte2 = file_size - 1
            
        length = byte2 - byte1 + 1
        
        headers["Content-Range"] = f"bytes {byte1}-{byte2}/{file_size}"
        headers["Content-Length"] = str(length)
        
        return StreamingResponse(
            file_iterator(file_path, byte1, length),
            status_code=206,
            headers=headers,
        )
    else:
        # İlk isteği de StreamingResponse ile döndür — FileResponse content-disposition: attachment
        # ekliyor ve bu tarayıcıda video oynatımını bozabiliyor
        headers["Content-Length"] = str(file_size)
        return StreamingResponse(
            file_iterator(file_path, 0, file_size),
            status_code=200,
            headers=headers,
        )


# ─── Helpers ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)

def load_db() -> dict:
    if not DB_PATH.exists():
        os.makedirs(DB_PATH.parent, exist_ok=True)
        data = {"clips": [], "stats": {"total_processed": 0, "total_uploaded": 0}}
        save_db(data)
        return data
    with open(DB_PATH) as f:
        return json.load(f)

def save_db(data: dict):
    os.makedirs(DB_PATH.parent, exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ─── Models ───────────────────────────────────────────────────────────────

class TextOverlay(BaseModel):
    text: str
    y_percent: Optional[int] = 50
    color: Optional[str] = "white"
    font_size: Optional[int] = 48  # 1080p bazında font boyutu
    duration: Optional[str] = "full"  # "full" or "custom"
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class ImageOverlay(BaseModel):
    filename: str
    x_percent: Optional[int] = 50
    y_percent: Optional[int] = 50
    opacity: Optional[float] = 1.0
    scale: Optional[float] = 0.2
    dvd_bounce: Optional[bool] = False
    duration: Optional[str] = "full"
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class SplitSettings(BaseModel):
    camX: int = 0
    camY: int = 0
    camW: int = 25
    autoTracking: bool = False
    blackBg: bool = False

class ClipRequest(BaseModel):
    source_filename: str
    start_time: str
    end_time: str
    channel: str  # anime, film, dizi
    title: str
    description: Optional[str] = ""
    hook_text: Optional[str] = None
    crop_mode: Optional[str] = "blur"
    margin_v: Optional[int] = 80
    add_subtitles: Optional[bool] = True
    subtitle_languages: Optional[list] = ["en"]
    hashtags: Optional[list] = None
    text_layers: Optional[list[TextOverlay]] = []
    image_layers: Optional[list[ImageOverlay]] = []
    split_settings: Optional[SplitSettings] = None
    preview_layout_filename: Optional[str] = None

class UploadRequest(BaseModel):
    clip_id: str
    platforms: list  # ["youtube", "tiktok", "instagram"]
    title: str
    description: Optional[str] = ""
    hashtags: Optional[list] = None
    schedule_time: Optional[str] = None

class DownloadRequest(BaseModel):
    url: str
    quality: Optional[str] = "1080"
    custom_name: Optional[str] = None
    format: Optional[str] = "mp4"


# ─── Routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(str(BASE_DIR / "frontend" / "index.html"))

def _run_download_with_progress(job_id: str, req_dict: dict):
    try:
        from downloader import download_media_generator
        sources_dir = MEDIA_DIR / "sources"
        
        for update in download_media_generator(
            url=req_dict["url"],
            quality=req_dict["quality"],
            output_dir=str(sources_dir),
            custom_name=req_dict.get("custom_name"),
            format=req_dict.get("format", "mp4")
        ):
            with _job_lock:
                # Update job with the yielded dict
                _jobs[job_id].update(update)
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        with _job_lock:
            _jobs[job_id].update({
                "status": "error",
                "message": f"Hata: {str(e)}"
            })

@app.post("/api/download/start")
async def start_download(req: DownloadRequest):
    """YouTube, Twitch, Kick üzerinden yayını/videoyu arka planda indirmeye başla"""
    job_id = "dl_" + uuid.uuid4().hex[:12]
    
    with _job_lock:
        _jobs[job_id] = {
            "status": "starting",
            "percent": 0,
            "message": "İndirme sırasına alındı...",
            "speed": "",
            "eta": "",
            "size": "",
            "filename": None
        }
        
    thread = threading.Thread(
        target=_run_download_with_progress,
        args=(job_id, req.dict()),
        daemon=True
    )
    thread.start()
    
    return {"job_id": job_id, "status": "started"}

@app.get("/api/download/stream/{job_id}")
async def stream_download_progress(job_id: str):
    """SSE ile gerçek zamanlı indirme ilerleme akışı"""
    async def event_generator():
        while True:
            job = _get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Job bulunamadı'})}\n\n"
                break
            
            yield f"data: {json.dumps(job, default=str)}\n\n"
            
            if job.get("status") in ("completed", "error"):
                break
            
            await asyncio.sleep(0.5)  # Hızlı güncellemeler için 0.5s
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@app.post("/api/upload-asset")
async def upload_asset(file: UploadFile = File(...)):
    """Logo vb. görselleri assets klasörüne yükle"""
    assets_dir = MEDIA_DIR / "assets"
    os.makedirs(assets_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file.filename)[1]
    safe_filename = f"asset_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = assets_dir / safe_filename
    
    with open(file_path, "wb") as buffer:
        import shutil
        shutil.copyfileobj(file.file, buffer)
        
    return {"filename": safe_filename, "success": True}

@app.get("/api/config")
async def get_config():
    """Kanal ve platform yapılandırmasını döndür"""
    return load_config()

@app.get("/api/sources")
async def list_sources():
    """Kaynak video dosyalarını listele"""
    sources_dir = MEDIA_DIR / "sources"
    files = []
    
    if sources_dir.exists():
        for f in sources_dir.iterdir():
            if f.suffix.lower() in [".mp4", ".mkv", ".avi", ".mov", ".webm", ".mpg", ".mpeg", ".ts"]:
                try:
                    info = get_video_info(str(f))
                    
                    # Thumbnail oluşturma
                    thumbs_dir = sources_dir / ".thumbnails"
                    os.makedirs(thumbs_dir, exist_ok=True)
                    thumb_path = thumbs_dir / f"{f.name}.jpg"
                    
                    if not thumb_path.exists() and info.get("duration", 0) > 0:
                        # ffmpeg ile hızlıca thumbnail al (5. saniye veya sürenin %10'u)
                        seek_time = min(5, info["duration"] * 0.1)
                        import subprocess
                        subprocess.run([
                            "ffmpeg", "-y", "-ss", str(seek_time),
                            "-i", str(f), "-vframes", "1",
                            "-q:v", "2", "-s", "320x180", str(thumb_path)
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                    thumb_url = f"/media/sources/.thumbnails/{f.name}.jpg" if thumb_path.exists() else None
                    
                    files.append({
                        "filename": f.name,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                        "duration": info["duration"],
                        "resolution": f"{info['width']}x{info['height']}",
                        "thumbnail": thumb_url
                    })
                except Exception:
                    files.append({
                        "filename": f.name,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                        "thumbnail": None
                    })
    
    return {"sources": files}


@app.post("/api/upload-source")
async def upload_source(file: UploadFile = File(...)):
    """Kaynak video yükle"""
    sources_dir = MEDIA_DIR / "sources"
    os.makedirs(sources_dir, exist_ok=True)
    
    filepath = sources_dir / file.filename
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)
    
    try:
        info = get_video_info(str(filepath))
    except Exception:
        info = {}
    
    return {
        "filename": file.filename,
        "size_mb": round(filepath.stat().st_size / 1024 / 1024, 1),
        "info": info,
    }


class HighlightRequest(BaseModel):
    source_filename: str

@app.post("/api/detect-highlights")
async def detect_highlights(req: HighlightRequest):
    """Videonun ses tepe noktalarını analiz eder"""
    source_path = MEDIA_DIR / "sources" / req.source_filename
    
    if not source_path.exists():
        raise HTTPException(404, f"Kaynak video bulunamadı: {req.source_filename}")
        
    try:
        from audio_analyzer import find_highlights
        highlights = find_highlights(str(source_path))
        return {"highlights": highlights}
    except Exception as e:
        raise HTTPException(500, f"Analiz hatası: {str(e)}")


# ─── Process Clip (Async with Progress) ──────────────────────────────────

def _run_pipeline_with_progress(job_id: str, req_dict: dict, config: dict):
    """Thread'de çalışan pipeline — her adım sonrası progress günceller"""
    try:
        from video_processor import (
            get_video_info, cut_clip, crop_to_vertical,
            add_watermark, add_hook_text, generate_subtitles,
            burn_subtitles, apply_advanced_layers, translate_srt,
            translate_text
        )

        source_path = str(MEDIA_DIR / "sources" / req_dict["source_filename"])
        channel = req_dict["channel"]
        base_clip_id = f"{channel}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"

        channel_config = config["channels"].get(channel, {})
        watermark_path = None
        wm_file = channel_config.get("watermark")
        if wm_file:
            wm_path = BASE_DIR / wm_file
            if wm_path.exists():
                watermark_path = str(wm_path)

        subtitle_langs = req_dict.get("subtitle_languages", ["en"])
        text_layers = req_dict.get("text_layers", [])
        image_layers = req_dict.get("image_layers", [])

        # Calculate total steps
        has_subs = req_dict.get("add_subtitles", True)
        has_hook = bool(req_dict.get("hook_text"))
        has_layers = (len(text_layers) > 0) or (len(image_layers) > 0)
        has_wm = watermark_path is not None

        # Steps: cut, crop, [whisper], then per-lang: [hook, sub, layers, wm, copy]
        base_steps = 2  # cut + crop
        if has_subs:
            base_steps += 1  # whisper
        per_lang_steps = 1  # final copy
        if has_hook:
            per_lang_steps += 1
        if has_subs:
            per_lang_steps += 1
        if has_layers:
            per_lang_steps += 1
        if has_wm:
            per_lang_steps += 1

        total_steps = base_steps + (per_lang_steps * len(subtitle_langs))
        current_step = 0

        clips_dir = MEDIA_DIR / "clips" / base_clip_id
        exports_dir = MEDIA_DIR / "exports" / base_clip_id
        os.makedirs(clips_dir, exist_ok=True)
        os.makedirs(exports_dir, exist_ok=True)

        base_file = source_path
        preview_layout_filename = req_dict.get("preview_layout_filename")

        if preview_layout_filename:
            # Frontend zaten trim ve crop yaptı, doğrudan bunu alıyoruz!
            current_step += 2
            _update_job(job_id, step="Önceden hazırlanan dikey video yükleniyor...", progress=int(current_step / total_steps * 100))
            crop_output = str(clips_dir / "02_vertical.mp4")
            preview_file_path = MEDIA_DIR / "preview_temp" / preview_layout_filename
            
            if preview_file_path.exists():
                shutil.copy2(str(preview_file_path), crop_output)
                slog(f"[process] Preview dosyasi kopyalandi: {preview_layout_filename}")
            else:
                raise Exception(f"Önizleme dosyası bulunamadı: {preview_layout_filename}")
                
            base_file = crop_output
        else:
            # Eski usul (Step 1 ve 2)
            current_step += 1
            _update_job(job_id, step="Video kesiliyor...", progress=int(current_step / total_steps * 100))
            slog(f"[process] Adim 1: Video kesiliyor...")
            cut_output = str(clips_dir / "01_cut.mp4")
            cut_clip(base_file, cut_output, req_dict["start_time"], req_dict["end_time"])
            base_file = cut_output
            slog(f"[process] Adim 1: Kesme OK")

            current_step += 1
            _update_job(job_id, step="Dikey formata dönüştürülüyor...", progress=int(current_step / total_steps * 100))
            slog(f"[process] Adim 2: Dikey format...")
            crop_output = str(clips_dir / "02_vertical.mp4")
            crop_to_vertical(
                base_file, 
                crop_output, 
                mode=req_dict.get("crop_mode", "blur"),
                split_settings=req_dict.get("split_settings")
            )
            base_file = crop_output
            slog(f"[process] Adim 2: Dikey format OK")

        # Step 3: Whisper (if needed)
        base_srt_path = None
        if has_subs:
            current_step += 1
            _update_job(job_id, step="Altyazı oluşturuluyor (Whisper AI)...", progress=int(current_step / total_steps * 100))
            slog(f"[process] Adim 3: Whisper altyazi...")
            base_srt_path = str(clips_dir / "subtitles_base.srt")
            generate_subtitles(base_file, base_srt_path, model=config.get("whisper_model", "base"), language="en")
            slog(f"[process] Adim 3: Whisper OK")

        results = []
        steps_log = [{"step": "cut"}, {"step": "crop"}]
        if has_subs:
            steps_log.append({"step": "subtitles"})

        # Per-language processing
        for lang in subtitle_langs:
            lang_file = base_file
            lang_srt = None
            slog(f"[process] Dil isleniyor: {lang}")

            # Hook text
            if has_hook:
                current_step += 1
                _update_job(job_id, step=f"Hook yazısı ekleniyor ({lang})...", progress=int(current_step / total_steps * 100))
                slog(f"[process] Hook text ekleniyor ({lang})...")
                translated_hook = translate_text(req_dict["hook_text"], lang) if req_dict["hook_text"] else None
                hook_output = str(clips_dir / f"03_hook_{lang}.mp4")
                add_hook_text(lang_file, hook_output, translated_hook)
                lang_file = hook_output
                slog(f"[process] Hook text OK ({lang})")

            # Subtitles
            if has_subs and base_srt_path:
                current_step += 1
                _update_job(job_id, step=f"Altyazı yakılıyor ({lang})...", progress=int(current_step / total_steps * 100))
                slog(f"[process] Altyazi yakilliyor ({lang})...")
                if lang == "en":
                    lang_srt = base_srt_path
                else:
                    lang_srt = translate_srt(base_srt_path, lang)
                sub_output = str(clips_dir / f"04_subtitled_{lang}.mp4")
                burn_subtitles(lang_file, sub_output, lang_srt, margin_v=req_dict.get("margin_v", 80))
                lang_file = sub_output
                slog(f"[process] Altyazi OK ({lang})")

            # Layers
            if has_layers:
                current_step += 1
                _update_job(job_id, step=f"Katmanlar ekleniyor ({lang})...", progress=int(current_step / total_steps * 100))
                slog(f"[process] Katmanlar ekleniyor ({lang})...")
                overlay_output = str(clips_dir / f"04b_layers_{lang}.mp4")
                apply_advanced_layers(lang_file, overlay_output, text_layers, image_layers)
                lang_file = overlay_output
                slog(f"[process] Katmanlar OK ({lang})")

            # Watermark
            if has_wm:
                current_step += 1
                _update_job(job_id, step=f"Watermark ekleniyor ({lang})...", progress=int(current_step / total_steps * 100))
                slog(f"[process] Watermark ekleniyor ({lang})...")
                wm_output = str(clips_dir / f"05_watermarked_{lang}.mp4")
                add_watermark(lang_file, wm_output, watermark_path)
                lang_file = wm_output
                slog(f"[process] Watermark OK ({lang})")

            # Final copy
            current_step += 1
            _update_job(job_id, step=f"Final export ({lang})...", progress=int(current_step / total_steps * 100))
            lang_clip_id = f"{base_clip_id}_{lang}" if len(subtitle_langs) > 1 else base_clip_id
            final_output = str(exports_dir / f"{channel}_{lang_clip_id}.mp4")
            if lang_file != final_output:
                shutil.copy2(lang_file, final_output)

            results.append({
                "clip_id": lang_clip_id,
                "channel": channel,
                "language": lang,
                "final_output": final_output,
                "srt_path": lang_srt,
            })
            slog(f"[process] Dil tamamlandi: {lang}")

        # Save to DB
        db = load_db()
        saved_clips = []
        for res in results:
            lang = res.get("language", "en")
            translated_title = translate_text(req_dict["title"], lang) if req_dict["title"] else req_dict["title"]
            translated_desc = translate_text(req_dict.get("description", ""), lang) if req_dict.get("description") else req_dict.get("description", "")

            clip_entry = {
                "clip_id": res["clip_id"],
                "channel": channel,
                "language": lang,
                "title": f"{translated_title}",
                "description": translated_desc,
                "hashtags": req_dict.get("hashtags") or channel_config.get("default_hashtags", []),
                "source": req_dict["source_filename"],
                "start_time": req_dict["start_time"],
                "end_time": req_dict["end_time"],
                "final_output": res["final_output"],
                "srt_path": res.get("srt_path"),
                "created_at": datetime.now().isoformat(),
                "uploaded_to": [],
                "status": "ready",
            }
            db["clips"].append(clip_entry)
            db["stats"]["total_processed"] += 1
            saved_clips.append(clip_entry)

        save_db(db)

        slog(f"[process] TAMAMLANDI! {len(saved_clips)} klip olusturuldu.")
        _update_job(job_id,
            status="done",
            progress=100,
            step="Tamamlandı!",
            result={
                "status": "ready",
                "clips": [{"clip_id": c["clip_id"], "language": c["language"], "output": c["final_output"]} for c in saved_clips],
                "steps": [s["step"] for s in steps_log],
            }
        )

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        slog(f"[process] KRITIK HATA: {err}")
        _update_job(job_id, status="error", error=str(e), step=f"Hata: {str(e)}")


class PreviewTrimRequest(BaseModel):
    source_filename: str
    start_time: str
    end_time: str

class PreviewLayoutRequest(BaseModel):
    trimmed_filename: str
    crop_mode: str
    split_settings: Optional[SplitSettings] = None

@app.post("/api/preview/trim")
def preview_trim(req: PreviewTrimRequest):
    slog(f"[API] /api/preview/trim istegi alindi: {req.source_filename} ({req.start_time} - {req.end_time})")
    temp_dir = MEDIA_DIR / "preview_temp"
    os.makedirs(temp_dir, exist_ok=True)
    out_id = uuid.uuid4().hex[:8]
    out_name = f"trim_{out_id}.mp4"
    out_path = str(temp_dir / out_name)
    source_path = str(MEDIA_DIR / "sources" / req.source_filename)
    
    if not os.path.exists(source_path):
        slog(f"[API] HATA: Kaynak bulunamadi ({source_path})")
        raise HTTPException(404, "Kaynak bulunamadı")
        
    try:
        slog(f"[API] cut_clip cagrilacak...")
        cut_clip(source_path, out_path, req.start_time, req.end_time)
        slog(f"[API] cut_clip basariyla dondu.")
        return {"filename": out_name, "url": f"/media/preview_temp/{out_name}"}
    except Exception as e:
        slog(f"[API] HATA (preview_trim): {str(e)}")
        raise HTTPException(500, str(e))

class PreviewCameraTrimRequest(BaseModel):
    trimmed_filename: str
    cam_x: int = 0
    cam_y: int = 0
    cam_w: int = 25


@app.post("/api/preview/trim-camera")
def preview_trim_camera(req: PreviewCameraTrimRequest):
    """Kesilmiş klipten kamera bölgesini ayrı bir dosya olarak çıkar"""
    temp_dir = MEDIA_DIR / "preview_temp"
    os.makedirs(temp_dir, exist_ok=True)
    out_id = uuid.uuid4().hex[:8]
    out_name = f"cam_{out_id}.mp4"
    out_path = str(temp_dir / out_name)
    trimmed_path = str(temp_dir / req.trimmed_filename)
    
    if not os.path.exists(trimmed_path):
        raise HTTPException(404, "Kesilmiş (trim) kaynak bulunamadı")
        
    try:
        from video_processor import get_video_info, _run_ffmpeg, get_video_codec_args, slog
        
        slog(f"[preview/trim-camera] trimmed={req.trimmed_filename} cam_x={req.cam_x} cam_y={req.cam_y} cam_w={req.cam_w}")
        
        info = get_video_info(trimmed_path)
        src_w, src_h = info["width"], info["height"]
        
        # Kamera crop hesapla (yüzde → piksel)
        cx_pct = req.cam_x / 100.0
        cy_pct = req.cam_y / 100.0
        cw_pct = req.cam_w / 100.0
        
        crop_w = int(src_w * cw_pct)
        crop_h = int(crop_w * (9/16))  # 9:16 aspect ratio
        crop_x = int(src_w * cx_pct)
        crop_y = int(src_h * cy_pct)
        
        # Sınırları kontrol et
        crop_x = min(crop_x, src_w - crop_w)
        crop_y = min(crop_y, src_h - crop_h)
        crop_x = max(0, crop_x)
        crop_y = max(0, crop_y)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", trimmed_path,
            "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=1080:1920",
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", "5M",
            "-c:a", "aac", "-b:a", "192k",
            out_path
        ]
        
        _run_ffmpeg(cmd, timeout=120, label="preview/trim-camera")
        
        return {"filename": out_name, "url": f"/media/preview_temp/{out_name}"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/preview/layout")
def preview_layout(req: PreviewLayoutRequest):
    temp_dir = MEDIA_DIR / "preview_temp"
    os.makedirs(temp_dir, exist_ok=True)
    out_id = uuid.uuid4().hex[:8]
    out_name = f"layout_{out_id}.mp4"
    out_path = str(temp_dir / out_name)
    trimmed_path = str(temp_dir / req.trimmed_filename)
    
    if not os.path.exists(trimmed_path):
        raise HTTPException(404, "Kesilmiş (trim) kaynak bulunamadı")
        
    try:
        from video_processor import crop_to_vertical, slog
        slog(f"[preview/layout] trimmed={req.trimmed_filename} crop_mode={req.crop_mode}")
        crop_to_vertical(trimmed_path, out_path, mode=req.crop_mode, 
                         split_settings=req.split_settings.dict() if req.split_settings else None,
                         force_cpu=True)
        slog(f"[preview/layout] Basarili: {out_name}")
        return {"filename": out_name, "url": f"/media/preview_temp/{out_name}"}
    except Exception as e:
        from video_processor import slog
        slog(f"[preview/layout] HATA: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/process")
async def process_clip(req: ClipRequest):
    """Video klibini arka planda işle, job_id döndür"""
    source_path = MEDIA_DIR / "sources" / req.source_filename
    
    if not source_path.exists():
        raise HTTPException(404, f"Kaynak video bulunamadı: {req.source_filename}")
    
    config = load_config()
    job_id = uuid.uuid4().hex[:12]
    
    req_dict = {
        "source_filename": req.source_filename,
        "start_time": req.start_time,
        "end_time": req.end_time,
        "channel": req.channel,
        "title": req.title,
        "description": req.description,
        "hook_text": req.hook_text,
        "crop_mode": req.crop_mode,
        "margin_v": req.margin_v,
        "add_subtitles": req.add_subtitles,
        "subtitle_languages": req.subtitle_languages,
        "hashtags": req.hashtags,
        "text_layers": [t.dict() for t in req.text_layers],
        "image_layers": [i.dict() for i in req.image_layers],
        "split_settings": req.split_settings.dict() if req.split_settings else None,
        "preview_layout_filename": req.preview_layout_filename,
    }

    with _job_lock:
        _jobs[job_id] = {
            "status": "running",
            "progress": 0,
            "step": "Başlatılıyor...",
            "error": None,
            "result": None,
        }

    thread = threading.Thread(
        target=_run_pipeline_with_progress,
        args=(job_id, req_dict, config),
        daemon=True
    )
    thread.start()

    return {"job_id": job_id, "status": "started"}


@app.get("/api/process/progress/{job_id}")
async def get_process_progress(job_id: str):
    """İşleme ilerleme durumunu döndür"""
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı")
    return job


@app.get("/api/process/stream/{job_id}")
async def stream_process_progress(job_id: str):
    """SSE ile gerçek zamanlı ilerleme akışı"""
    async def event_generator():
        while True:
            job = _get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'status': 'error', 'error': 'Job bulunamadı'})}\n\n"
                break
            
            yield f"data: {json.dumps(job, default=str)}\n\n"
            
            if job.get("status") in ("done", "error"):
                break
            
            await asyncio.sleep(0.8)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/clips")
async def list_clips():
    """İşlenmiş klipleri listele"""
    db = load_db()
    return {"clips": db["clips"], "stats": db["stats"]}


@app.get("/api/clips/{clip_id}/preview")
async def preview_clip(request: Request, clip_id: str):
    """Klibin önizleme videosunu döndür"""
    db = load_db()
    clip = next((c for c in db["clips"] if c["clip_id"] == clip_id), None)
    
    if not clip:
        raise HTTPException(404, "Klip bulunamadı")
    
    output_path = clip["final_output"]
    if not os.path.exists(output_path):
        raise HTTPException(404, "Video dosyası bulunamadı")
    
    return range_requests_response(request, output_path, "video/mp4")


@app.get("/api/sources/{filename:path}/stream")
async def stream_source(request: Request, filename: str):
    """Kaynak videoyu scrubbing (ileri-geri sarma) destekli olarak yayınlar"""
    source_path = MEDIA_DIR / "sources" / filename
    if not source_path.exists():
        raise HTTPException(404, "Kaynak video bulunamadı")
    return range_requests_response(request, str(source_path), "video/mp4")


@app.delete("/api/clips/{clip_id}")
async def delete_clip(clip_id: str):
    """Klibi sil"""
    db = load_db()
    clip = next((c for c in db["clips"] if c["clip_id"] == clip_id), None)
    
    if not clip:
        raise HTTPException(404, "Klip bulunamadı")
    
    # Dosyaları sil
    clips_dir = MEDIA_DIR / "clips" / clip_id
    exports_dir = MEDIA_DIR / "exports" / clip_id
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
    if exports_dir.exists():
        shutil.rmtree(exports_dir)
    
    db["clips"] = [c for c in db["clips"] if c["clip_id"] != clip_id]
    save_db(db)
    
    return {"status": "deleted", "clip_id": clip_id}


@app.post("/api/upload")
async def upload_to_platforms(req: UploadRequest):
    """Klibi seçilen platformlara yükle"""
    db = load_db()
    clip = next((c for c in db["clips"] if c["clip_id"] == req.clip_id), None)
    
    if not clip:
        raise HTTPException(404, "Klip bulunamadı")
    
    results = {}
    config = load_config()
    channel_config = config["channels"].get(clip["channel"], {})
    
    hashtags = req.hashtags or clip.get("hashtags", [])
    hashtag_str = " ".join(hashtags)
    full_description = f"{req.description}\n\n{hashtag_str}" if req.description else hashtag_str
    
    # YouTube
    if "youtube" in req.platforms:
        try:
            from uploaders.youtube import upload_short
            yt_result = upload_short(
                video_path=clip["final_output"],
                title=req.title,
                description=full_description,
                tags=hashtags,
                schedule_time=req.schedule_time,
            )
            results["youtube"] = yt_result
            clip["uploaded_to"].append({
                "platform": "youtube",
                "url": yt_result.get("url"),
                "uploaded_at": datetime.now().isoformat(),
            })
        except Exception as e:
            results["youtube"] = {"error": str(e)}
    
    # TikTok
    if "tiktok" in req.platforms:
        try:
            from uploaders.tiktok import TikTokUploader
            tt = TikTokUploader()
            if tt.is_authenticated():
                import asyncio
                tt_result = await tt.init_upload(
                    video_path=clip["final_output"],
                    title=f"{req.title} {hashtag_str}",
                )
                results["tiktok"] = tt_result
                clip["uploaded_to"].append({
                    "platform": "tiktok",
                    "uploaded_at": datetime.now().isoformat(),
                })
            else:
                results["tiktok"] = {"error": "TikTok kimlik doğrulaması gerekli"}
        except Exception as e:
            results["tiktok"] = {"error": str(e)}
    
    # Instagram
    if "instagram" in req.platforms:
        try:
            from uploaders.instagram import InstagramUploader
            ig = InstagramUploader()
            if ig.is_authenticated():
                ig_result = await ig.upload_reel(
                    video_url="",  # Hosting URL gerekli
                    caption=f"{req.title}\n\n{full_description}",
                )
                results["instagram"] = ig_result
            else:
                results["instagram"] = {"error": "Instagram kimlik doğrulaması gerekli"}
        except Exception as e:
            results["instagram"] = {"error": str(e)}
    
    db["stats"]["total_uploaded"] += len([r for r in results.values() if "error" not in r])
    save_db(db)
    
    return {"clip_id": req.clip_id, "results": results}


@app.get("/api/platforms/status")
async def platform_status():
    """Tüm platformların bağlantı durumunu kontrol et"""
    status = {}
    
    # YouTube
    try:
        from uploaders.youtube import check_auth_status
        status["youtube"] = check_auth_status()
    except Exception as e:
        status["youtube"] = {"authenticated": False, "error": str(e)}
    
    # TikTok
    try:
        from uploaders.tiktok import TikTokUploader
        tt = TikTokUploader()
        status["tiktok"] = tt.check_status()
    except Exception as e:
        status["tiktok"] = {"authenticated": False, "error": str(e)}
    
    # Instagram
    try:
        from uploaders.instagram import InstagramUploader
        ig = InstagramUploader()
        status["instagram"] = ig.check_status()
    except Exception as e:
        status["instagram"] = {"authenticated": False, "error": str(e)}
    
    return status


@app.get("/api/system/status")
async def system_status():
    """Sistem gereksinimlerini kontrol et"""
    status = {"ffmpeg": False, "whisper": False}
    
    # Check FFmpeg
    try:
        import subprocess
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if result.returncode == 0:
            status["ffmpeg"] = True
    except Exception:
        pass
        
    # Check Whisper
    try:
        import whisper
        status["whisper"] = True
    except ImportError:
        pass
        
    return status


@app.get("/api/stats")
async def get_stats():
    """Dashboard istatistiklerini döndür"""
    db = load_db()
    
    today = datetime.now().strftime("%Y-%m-%d")
    today_clips = [c for c in db["clips"] if c["created_at"].startswith(today)]
    
    return {
        "total_processed": db["stats"]["total_processed"],
        "total_uploaded": db["stats"]["total_uploaded"],
        "total_clips": len(db["clips"]),
        "today_clips": len(today_clips),
        "ready_clips": len([c for c in db["clips"] if c["status"] == "ready"]),
        "by_channel": {
            "anime": len([c for c in db["clips"] if c["channel"] == "anime"]),
            "film": len([c for c in db["clips"] if c["channel"] == "film"]),
            "dizi": len([c for c in db["clips"] if c["channel"] == "dizi"]),
        }
    }


# ─── Startup ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("\n[ClipEngine] Baslatiliyor...")
    print("[Dashboard] http://localhost:8899")
    print("[API Docs]  http://localhost:8899/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8899)
