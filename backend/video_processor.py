"""
ClipEngine - Video Processing Module
FFmpeg tabanlı video işleme: kesme, crop, altyazı, watermark
"""

import subprocess
import os
import sys
import json
import tempfile
import re
from pathlib import Path


def _get_font_path() -> str:
    """Platforma göre uygun font dosyasını bul"""
    if sys.platform == "win32":
        return "/Windows/Fonts/arial.ttf"
    # Linux / Docker
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return "Sans"


BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = BASE_DIR / "media"


_best_encoder = None

def get_video_codec_args() -> list:
    """Sisteme en uygun donanım hızlandırmalı video encoder'ı bulur."""
    global _best_encoder
    if _best_encoder is not None:
        return _best_encoder
        
    import tempfile
    
    encoders = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
    
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
        
    _best_encoder = ["-c:v", "libx264", "-preset", "veryfast"] # Default fallback
    
    for enc in encoders[:-1]:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1", "-c:v", enc, tmp_path]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=5)
            if res.returncode == 0:
                _best_encoder = ["-c:v", enc]
                break
        except Exception:
            pass
            
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass
        
    print(f"[DEBUG] Video Encoder: {' '.join(_best_encoder)}")
    return _best_encoder


def get_video_info(video_path: str) -> dict:
    """Video hakkında bilgi al (süre, çözünürlük, fps)"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    data = json.loads(result.stdout)
    
    video_stream = next(
        (s for s in data.get("streams", []) if s["codec_type"] == "video"), 
        None
    )
    
    if not video_stream:
        raise ValueError("Video stream bulunamadı")
    
    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "duration": float(data["format"]["duration"]),
        "fps": eval(video_stream.get("r_frame_rate", "30/1")),
        "codec": video_stream["codec_name"],
    }


def cut_clip(
    source_path: str, 
    output_path: str, 
    start_time: str, 
    end_time: str
) -> str:
    """Videodan belirli bir bölümü kes
    
    Args:
        source_path: Kaynak video yolu
        output_path: Çıkış yolu
        start_time: Başlangıç zamanı (HH:MM:SS veya saniye)
        end_time: Bitiş zamanı (HH:MM:SS veya saniye)
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-to", str(end_time),
        "-i", source_path,
        "-c", "copy",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg hata: {result.stderr}")
    
    return output_path


def crop_to_vertical(
    input_path: str, 
    output_path: str, 
    mode: str = "blur",
    split_settings: dict = None
) -> str:
    """16:9 videoyu 9:16'ya çevir
    
    Args:
        mode: 
            "blur" - Arkaplana bulanık versiyon koy (en popüler)
            "crop" - Ortadan kes
            "fit" - Siyah barlarla sığdır
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    info = get_video_info(input_path)
    
    target_w, target_h = 1080, 1920
    
    if mode == "blur":
        # Arka planı bulanıklaştır + ortaya orijinal videoyu biraz daha zoomlu (örneğin 1080x900) koy
        filter_complex = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},boxblur=20:5[bg];"
            f"[0:v]scale=-2:900,crop={target_w}:900[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
        )
    elif mode == "split":
        # Yayıncı Modu: Üstte Kamera (Facecam), Altta Oyun/Ana İçerik
        if not split_settings:
            split_settings = {"camX": 0, "camY": 0, "camW": 25, "autoTracking": False, "blackBg": False}
            
        cx_pct = split_settings.get("camX", 0) / 100.0
        cy_pct = split_settings.get("camY", 0) / 100.0
        cw_pct = split_settings.get("camW", 25) / 100.0
        use_black_bg = split_settings.get("blackBg", False)
        
        # Orijinal video çözünürlüğüne göre kamerayı kes
        # Kamera kesimi: crop=w=iw*cw_pct:h=iw*cw_pct*(9/16):x=iw*cx_pct:y=ih*cy_pct
        cam_crop = f"crop=iw*{cw_pct}:iw*{cw_pct}*(9/16):iw*{cx_pct}:ih*{cy_pct}"
        
        # Kamera yüksekliği: 1080 genişliğe scale edilince 16:9 kamera ~608px olur
        cam_h = int(target_w * 9 / 16)  # ~608px
        cam_top = 0
        
        # Kamera ile oyun arası boşluk (metin katmanı için yer bırak)
        # Siyah bölge (gap) biraz daha büyütüldü (160 -> 240)
        gap = 240
        game_top = cam_h + gap
        # Oyun kalan alanı doldursun
        game_h = target_h - game_top
        
        if use_black_bg:
            # Siyah arkaplan — color source ile, video süresine uyması için shortest overlay kullanacağız
            bg_filter = (
                f"color=c=black:s={target_w}x{target_h}:r=30,format=yuv420p[bg]"
            )
        else:
            # Bulanık arkaplan
            bg_filter = (
                f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},boxblur=30:5,eq=brightness=-0.1[bg]"
            )
        
        filter_complex = (
            # Arka plan
            f"{bg_filter};"
            
            # Üst Kısım: Facecam (üstten cam_top px boşluk)
            f"[0:v]{cam_crop},scale=1080:-2[cam];"
            
            # Alt Kısım: Oyun (Daha büyük zoom)
            f"[0:v]scale=-2:{game_h},crop={target_w}:{game_h}[game];"
            
            # Üst üste bindir (shortest=1 ile video süresinde kes)
            f"[bg][cam]overlay=0:{cam_top}:shortest=1[bg_cam];"
            f"[bg_cam][game]overlay=0:{game_top}[out]"
        )
    elif mode == "crop":
        # Ortadan kes
        filter_complex = (
            f"[0:v]scale=-2:{target_h},"
            f"crop={target_w}:{target_h}[out]"
        )
    else:  # fit
        # Siyah barlarla sığdır (Yine zoomlu, 1080x900)
        filter_complex = (
            f"[0:v]scale=-2:900,crop={target_w}:900,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black[out]"
        )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "0:a?",
        *get_video_codec_args(),
        "-b:v", "8M",
        "-c:a", "aac",
        "-b:a", "192k",
        "-r", "30",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg hata: {result.stderr}")
    
    return output_path


def add_watermark(
    input_path: str, 
    output_path: str, 
    watermark_path: str,
    position: str = "top-right",
    opacity: float = 0.7,
    scale: float = 0.12
) -> str:
    """Videoya watermark (logo) ekle
    
    Args:
        position: top-left, top-right, bottom-left, bottom-right
        opacity: Saydamlık (0.0-1.0)
        scale: Logo boyutu (video genişliğine oranla)
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Pozisyon hesapla
    padding = 20
    pos_map = {
        "top-left": f"x={padding}:y={padding}",
        "top-right": f"x=W-w-{padding}:y={padding}",
        "bottom-left": f"x={padding}:y=H-h-{padding}",
        "bottom-right": f"x=W-w-{padding}:y=H-h-{padding}",
    }
    pos = pos_map.get(position, pos_map["top-right"])
    
    filter_complex = (
        f"[1:v]scale=iw*{scale}:-1,format=rgba,"
        f"colorchannelmixer=aa={opacity}[wm];"
        f"[0:v][wm]overlay={pos}[out]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-i", watermark_path,
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "0:a?",
        *get_video_codec_args(),
        "-b:v", "8M",
        "-c:a", "aac",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg hata: {result.stderr}")
    
    return output_path


def add_hook_text(
    input_path: str,
    output_path: str,
    text: str,
    duration: float = 3.0,
    font_size: int = 48,
    position: str = "center"
) -> str:
    """Videonun başına dikkat çekici yazı ekle (hook text)
    
    Args:
        text: Gösterilecek metin
        duration: Metnin ekranda kalma süresi (saniye)
        font_size: Font boyutu
        position: center, top, bottom
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Pozisyon
    y_map = {
        "center": "(h-text_h)/2",
        "top": "h*0.15",
        "bottom": "h*0.75",
    }
    y_pos = y_map.get(position, y_map["center"])
    
    # Escape special characters for FFmpeg drawtext
    escaped_text = text.replace("'", "'\\''").replace(":", "\\:")
    
    drawtext = (
        f"drawtext=text='{escaped_text}':"
        f"fontsize={font_size}:fontcolor=white:"
        f"borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:y={y_pos}:"
        f"enable='between(t,0,{duration})':"
        f"fontfile={_get_font_path()}"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", drawtext,
        *get_video_codec_args(),
        "-b:v", "8M",
        "-c:a", "copy",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg hata: {result.stderr}")
    
    return output_path


def generate_subtitles(
    input_path: str, 
    output_srt: str = None,
    model: str = "base",
    language: str = None
) -> str:
    """Whisper AI ile otomatik altyazı oluştur
    
    Args:
        model: tiny, base, small, medium, large
        language: Dil kodu (None = otomatik algıla)
    """
    try:
        import whisper
    except ImportError:
        raise ImportError("Whisper yüklü değil: pip install openai-whisper")
    
    if output_srt is None:
        base = os.path.splitext(input_path)[0]
        output_srt = f"{base}.srt"
    
    os.makedirs(os.path.dirname(output_srt) if os.path.dirname(output_srt) else ".", exist_ok=True)
    
    # Whisper ile transkripsiyon
    whisper_model = whisper.load_model(model)
    options = {}
    if language:
        if language == "en":
            options["task"] = "translate"
        else:
            options["language"] = language
    
    result = whisper_model.transcribe(input_path, **options)
    
    # SRT formatına çevir
    srt_content = []
    for i, segment in enumerate(result["segments"], 1):
        start = _format_timestamp(segment["start"])
        end = _format_timestamp(segment["end"])
        text = segment["text"].strip()
        wrapped_text = wrap_text(text, 30)
        srt_content.append(f"{i}\n{start} --> {end}\n{wrapped_text}\n")
    
    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_content))
    
    return output_srt


def burn_subtitles(
    input_path: str,
    output_path: str,
    srt_path: str,
    font_size: int = 18,
    margin_v: int = 80
) -> str:
    """SRT altyazıyı videoya yak (hardcode)
    
    Args:
        font_size: Font boyutu (ASS formatı, 1080p video için ölçeklenir)
        margin_v: Alt kenardan piksel cinsinden mesafe (ASS koordinat sistemi)
    """
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Gerçek video boyutlarını al
    try:
        info = get_video_info(input_path)
        real_h = info["height"]
        real_w = info["width"]
    except Exception:
        real_h = 1920
        real_w = 1080
    
    # ASS altyazılarında varsayılan ekran boyutu 384x288'dir.
    # FFmpeg MarginV değerini buna göre çok büyütüyordu.
    # PlayResX ve PlayResY'yi gerçek video boyutuna ayarlayarak 
    # MarginV'yi ve FontSize'ı birebir piksel olarak kullanacağız.
    # 288p deki 18 punto font, 1920p de yaklaşık 120 puntodur.
    ass_font_size = max(10, int(font_size * (real_h / 288.0)))
    ass_margin_v = max(0, int(margin_v * (real_h / 1920.0)))
    ass_outline = max(1.5, 2.5 * (real_h / 1920.0))
    ass_shadow = max(1.0, 1.5 * (real_h / 1920.0))
    
    # Windows yolu düzelt (FFmpeg subtitles filtresi için)
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    
    subtitle_filter = (
        f"subtitles='{srt_escaped}':"
        f"force_style='PlayResX={real_w},PlayResY={real_h},"
        f"FontName=Arial,FontSize={ass_font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline={ass_outline:.1f},Shadow={ass_shadow:.1f},"
        f"MarginV={ass_margin_v},"
        f"Alignment=2'"
    )
    
    print(f"[DEBUG] Subtitle: font={ass_font_size}, marginV={ass_margin_v}, video={real_w}x{real_h}")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", subtitle_filter,
        *get_video_codec_args(),
        "-b:v", "8M",
        "-c:a", "copy",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg hata: {result.stderr}")
    
    return output_path


def translate_srt(srt_path: str, target_lang: str) -> str:
    """SRT dosyasını deep-translator ile çevirir"""
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        return srt_path
        
    translator = GoogleTranslator(source='auto', target=target_lang)
    
    with open(srt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    translated_lines = []
    text_buffer = []
    text_indices = []
    
    for i, line in enumerate(lines):
        if "-->" in line or line.strip().isdigit() or not line.strip():
            translated_lines.append(line)
        else:
            translated_lines.append(None) # placeholder
            text_buffer.append(line.strip())
            text_indices.append(i)
            
    # Batch translation to speed up
    if text_buffer:
        try:
            # Google Translate limits batch to 5k chars, but SRT lines are short
            # Process in chunks of 50
            chunk_size = 50
            translated_texts = []
            for i in range(0, len(text_buffer), chunk_size):
                chunk = text_buffer[i:i+chunk_size]
                chunk_str = " | ".join(chunk) # use delimiter
                t_str = translator.translate(chunk_str)
                # split back
                t_chunks = []
                if t_str:
                    t_chunks = [s.strip() for s in t_str.split(" | ")]
                    
                # If delimiter fails, fallback to line by line
                if len(t_chunks) != len(chunk):
                    t_chunks = [(translator.translate(c) or c) for c in chunk]
                
                translated_texts.extend(t_chunks)
                
            for idx, trans in zip(text_indices, translated_texts):
                if trans is None:
                    trans = ""
                wrapped_trans = wrap_text(trans, 30)
                translated_lines[idx] = wrapped_trans + "\n"
        except Exception as e:
            print(f"Çeviri hatası: {e}")
            return srt_path
            
    new_srt_path = srt_path.replace(".srt", f"_{target_lang}.srt")
    with open(new_srt_path, "w", encoding="utf-8") as f:
        f.writelines(translated_lines)
        
    return new_srt_path


def wrap_text(text: str, max_length: int = 30) -> str:
    """Metni belirtilen karakter sınırında kelime bazlı alt satıra atar"""
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        if current_length + len(word) + 1 > max_length and current_line:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)
        else:
            current_line.append(word)
            current_length += len(word) + 1
            
    if current_line:
        lines.append(" ".join(current_line))
        
    return "\n".join(lines)


def translate_text(text: str, target_lang: str) -> str:
    """Metni deep-translator ile belirtilen dile çevirir"""
    if not text:
        return ""
        
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source='auto', target=target_lang).translate(text)
        return result if result is not None else text
    except ImportError:
        return text
    except Exception as e:
        print(f"Metin çeviri hatası: {e}")
        return text


def apply_advanced_layers(input_path: str, output_path: str, text_layers: list, image_layers: list = None) -> str:
    """Videoya çoklu metin ve görsel katmanları ekler
    
    Ölçeklendirme: Tüm y_percent değerleri 1080x1920 çıkış videosuna göre hesaplanır.
    Önizleme tarafı da aynı yüzde sistemini kullanır.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Gerçek video boyutlarını al (ölçek hesabı için)
    try:
        info = get_video_info(input_path)
        real_w = info["width"]
        real_h = info["height"]
    except Exception:
        real_w = 1080
        real_h = 1920
    
    cmd = ["ffmpeg", "-y", "-i", input_path]
    filter_chains = []
    
    # Görsel dosyalarını input olarak ekle
    image_layers = image_layers or []
    for img in image_layers:
        asset_path = MEDIA_DIR / "assets" / img["filename"]
        cmd.extend(["-i", str(asset_path)])
        
    last_video_pad = "[0:v]"
    
    # 1. Yazı Katmanları (Aynı video akışı üzerinde zincirleme)
    text_filters = []
    font_path = _get_font_path()
    
    for t in (text_layers or []):
        text = t.get("text", "")
        if not text:
            continue
            
        y_percent = t.get("y_percent", 50)
        color = t.get("color", "white")
        duration = t.get("duration", "full")
        st = t.get("start_time")
        et = t.get("end_time")
        font_size = t.get("font_size", 48)  # Frontend'den gelen boyut (1080p baz)
        
        # Y pozisyonu: text_h/2 çıkararak merkeze hizala
        y_expr = f"h*{y_percent/100}-text_h/2"
        
        # Font boyutunu video genişliğine göre 1:1 ölçekle (önizleme ile birebir eşleşsin)
        scale_factor = real_w / 1080.0
        scaled_font_size = max(12, int(font_size * scale_factor))
        border_w = max(2, int(3 * scale_factor))
        shadow_offset = max(1, int(2 * scale_factor))
        
        # Sadece CR karakterini temizle, kullanıcının girdiği \n satır atlamalarını koru!
        clean_text = text.replace('\r', '')
        
        # Emoji ve FFmpeg fontunun renderleyemediği özel karakterleri temizle (□ kutu sorunu)
        import re
        clean_text = re.sub(r'[^\w\s.,;:!?\'"-()\[\]{}@#$%&*+=/\\<>~`^|]', '', clean_text, flags=re.UNICODE)
        # Kalan görünmez/kontrol karakterlerini sil (fakat \n korunmalı)
        clean_text = ''.join(c for c in clean_text if c == ' ' or c == '\n' or c.isprintable()).strip()
        
        # Word wrap: Tarayıcının greedy algoritmasını taklit et
        usable_width = real_w * 0.92
        # Ortalama karakter genişliğini ARTTIRDIK ki daha erken alt satıra geçsin (Önizleme ile eşleşsin)
        avg_char_width = scaled_font_size * 0.56
        max_chars_per_line = max(10, int(usable_width / avg_char_width))
        
        wrapped_lines = []
        for raw_line in clean_text.split('\n'):
            words = raw_line.split()
            if not words:
                wrapped_lines.append("")
                continue
                
            current_line = []
            current_len = 0
            for word in words:
                new_len = current_len + len(word) + (1 if current_line else 0)
                if new_len > max_chars_per_line and current_line:
                    wrapped_lines.append(' '.join(current_line))
                    current_line = [word]
                    current_len = len(word)
                else:
                    current_line.append(word)
                    current_len = new_len
            if current_line:
                wrapped_lines.append(' '.join(current_line))
                
        # FFmpeg filter escape kuralları ve Kutu bug'ı çözümü:
        # Windows'ta text parametresi veya textfile içine konulan '\n' karakteri drawtext 
        # tarafından glyph (kutu) olarak çizilebiliyor. Bu yüzden ÇOKLU SATIRLARI 
        # tek bir text='...' ile vermek yerine her satır için ayrı bir drawtext ekliyoruz.
        dt_list = []
        line_spacing = int(10 * scale_factor)
        num_lines = len(wrapped_lines)
        total_h_expr = f"({num_lines}*line_h+{max(0, num_lines-1)}*{line_spacing})"
        
        enable_str = ""
        if duration == "custom" and st and et:
            def to_seconds(time_str):
                parts = str(time_str).replace(',', '.').split(':')
                if len(parts) == 1: return float(parts[0])
                elif len(parts) == 2: return float(parts[0])*60 + float(parts[1])
                else: return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
            try:
                start_s = to_seconds(st)
                end_s = to_seconds(et)
                enable_str = f":enable='between(t,{start_s},{end_s})'"
            except:
                pass

        for i, line_text in enumerate(wrapped_lines):
            esc_line = line_text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace(",", "\\,")
            if not esc_line.strip():
                continue
                
            y_expr = f"h*({y_percent}/100)-{total_h_expr}/2+{i}*(line_h+{line_spacing})"
            
            dt = (
                f"drawtext=text='{esc_line}'"
                f":fontfile='{font_path}'"
                f":fontsize={scaled_font_size}"
                f":fontcolor={color}"
                f":borderw={border_w}"
                f":bordercolor=black"
                f":shadowcolor=black@0.5"
                f":shadowx={shadow_offset}:shadowy={shadow_offset}"
                f":x=(w-text_w)/2"
                f":y={y_expr}"
            )
            dt += enable_str
            dt_list.append(dt)
            
        text_filters.extend(dt_list)
        
    if text_filters:
        # Metin filtrelerini 0:v üzerinde ardışık uygula
        filter_chains.append(f"{last_video_pad}{','.join(text_filters)}[v_text]")
        last_video_pad = "[v_text]"
        
    # 2. Görsel Katmanları (Logo, DVD Bounce)
    for i, img in enumerate(image_layers):
        in_idx = i + 1  # 0 video, 1 img1, 2 img2 vb.
        
        scale = img.get("scale", 0.5)
        opacity = img.get("opacity", 1.0)
        y_percent = img.get("y_percent", 50)
        dvd_bounce = img.get("dvd_bounce", False)
        
        # Görseli hazırla: video genişliğine oranla ölçekle
        # scale=0.5 => videonun %50 genişliğinde
        img_target_w = int(real_w * scale)
        img_prep = f"[{in_idx}:v]scale={img_target_w}:-1"
        if opacity < 1.0:
            img_prep += f",format=rgba,colorchannelmixer=aa={opacity}"
        img_prep += f"[img{in_idx}]"
        filter_chains.append(img_prep)
        
        # Overlay işlemi
        next_pad = f"[v_img{in_idx}]"
        if dvd_bounce:
            # Ekranda zıplayan hareket mantığı
            x_expr = "abs(W-w - mod(t*150, 2*(W-w)))"
            y_expr = "abs(H-h - mod(t*100, 2*(H-h)))"
            filter_chains.append(f"{last_video_pad}[img{in_idx}]overlay=x='{x_expr}':y='{y_expr}'{next_pad}")
        else:
            # Y pozisyonu: y_percent merkez noktası, h/2 çıkararak ortala
            # X pozisyonu: Sola hizalı (W*0.04) frontend preview ile aynı olması için
            y_expr = f"H*{y_percent/100}-h/2"
            filter_chains.append(f"{last_video_pad}[img{in_idx}]overlay=x=W*0.04:y={y_expr}{next_pad}")
            
        last_video_pad = next_pad

    if not filter_chains:
        import shutil
        shutil.copy2(input_path, output_path)
        return output_path
        
    filter_complex = ";".join(filter_chains)
    
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", last_video_pad,
        "-map", "0:a",
        *get_video_codec_args(), "-b:v", "8M",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ])
    
    print(f"[DEBUG] FFmpeg layer cmd: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        print(f"Layer uyarı: {result.stderr}")
        import shutil
        shutil.copy2(input_path, output_path)
        
    return output_path


def full_pipeline(
    source_path: str,
    clip_id: str,
    start_time: str,
    end_time: str,
    channel: str,
    crop_mode: str = "blur",
    hook_text: str = None,
    add_subs: bool = True,
    whisper_model: str = "base",
    subtitle_langs: list = None,
    margin_v: int = 80,
    watermark_path: str = None,
    text_layers: list = None,
    image_layers: list = None,
    split_settings: dict = None,
) -> list:
    """Tam pipeline: kes → crop → (hook & altyazı & watermark x dil) → export
    
    Returns:
        list: Her bir dil için oluşturulan klip sonuçları
    """
    if subtitle_langs is None:
        subtitle_langs = ["en"]
        
    clips_dir = MEDIA_DIR / "clips" / clip_id
    exports_dir = MEDIA_DIR / "exports" / clip_id
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(exports_dir, exist_ok=True)
    
    steps = []
    base_file = source_path
    
    # 1. Klip kes
    cut_output = str(clips_dir / "01_cut.mp4")
    cut_clip(base_file, cut_output, start_time, end_time)
    base_file = cut_output
    steps.append({"step": "cut", "output": cut_output})
    
    # 2. 9:16 crop
    crop_output = str(clips_dir / "02_vertical.mp4")
    crop_to_vertical(base_file, crop_output, mode=crop_mode, split_settings=split_settings)
    base_file = crop_output
    steps.append({"step": "crop", "output": crop_output})
    
    # 3. Whisper Base Altyazı
    base_srt_path = None
    if add_subs:
        base_srt_path = str(clips_dir / "subtitles_base.srt")
        generate_subtitles(base_file, base_srt_path, model=whisper_model, language="en")
    
    results = []
    
    # Her dil için videoyu ayrı ayrı tamamla
    for lang in subtitle_langs:
        lang_file = base_file
        lang_srt = None
        lang_steps = list(steps)
        
        # 4. Hook text (Dile özel)
        if hook_text:
            translated_hook = translate_text(hook_text, lang) if hook_text else None
            hook_output = str(clips_dir / f"03_hook_{lang}.mp4")
            add_hook_text(lang_file, hook_output, translated_hook)
            lang_file = hook_output
            lang_steps.append({"step": f"hook_text_{lang}", "output": hook_output})
            
        # 5. Dile Özel Altyazı Çevirisi ve Gömülmesi
        if add_subs and base_srt_path:
            if lang == "en":
                lang_srt = base_srt_path
            else:
                lang_srt = translate_srt(base_srt_path, lang)
                
            sub_output = str(clips_dir / f"04_subtitled_{lang}.mp4")
            burn_subtitles(lang_file, sub_output, lang_srt, margin_v=margin_v)
            lang_file = sub_output
            lang_steps.append({"step": f"subtitles_{lang}", "output": sub_output, "srt": lang_srt})
        
        # 5.5. Katmanlar (Layers)
        if (text_layers and len(text_layers) > 0) or (image_layers and len(image_layers) > 0):
            overlay_output = str(clips_dir / f"04b_layers_{lang}.mp4")
            apply_advanced_layers(lang_file, overlay_output, text_layers, image_layers)
            lang_file = overlay_output
            lang_steps.append({"step": f"layers_{lang}", "output": overlay_output})
            
        # 6. Watermark
        if watermark_path and os.path.exists(watermark_path):
            wm_output = str(clips_dir / f"05_watermarked_{lang}.mp4")
            add_watermark(lang_file, wm_output, watermark_path)
            lang_file = wm_output
            lang_steps.append({"step": f"watermark_{lang}", "output": wm_output})
            
        # 7. Final export
        lang_clip_id = f"{clip_id}_{lang}" if len(subtitle_langs) > 1 else clip_id
        final_output = str(exports_dir / f"{channel}_{lang_clip_id}.mp4")
        
        if lang_file != final_output:
            import shutil
            shutil.copy2(lang_file, final_output)
            
        results.append({
            "clip_id": lang_clip_id,
            "channel": channel,
            "language": lang,
            "final_output": final_output,
            "srt_path": lang_srt,
            "steps": lang_steps,
        })
        
    return results


def _format_timestamp(seconds: float) -> str:
    """Saniyeyi SRT zaman damgasına çevir: HH:MM:SS,mmm"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"
