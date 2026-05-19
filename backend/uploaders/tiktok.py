"""
ClipEngine - TikTok Uploader
TikTok Content Posting API entegrasyonu
"""

import httpx
import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent
TIKTOK_CONFIG_PATH = BASE_DIR / "credentials" / "tiktok_config.json"


class TikTokUploader:
    """TikTok Content Posting API ile video yükleme"""
    
    BASE_URL = "https://open.tiktokapis.com/v2"
    
    def __init__(self):
        self.access_token = None
        self.open_id = None
        self._load_config()
    
    def _load_config(self):
        """Kayıtlı token bilgilerini yükle"""
        if TIKTOK_CONFIG_PATH.exists():
            with open(TIKTOK_CONFIG_PATH) as f:
                config = json.load(f)
                self.access_token = config.get("access_token")
                self.open_id = config.get("open_id")
    
    def _save_config(self):
        """Token bilgilerini kaydet"""
        os.makedirs(TIKTOK_CONFIG_PATH.parent, exist_ok=True)
        with open(TIKTOK_CONFIG_PATH, "w") as f:
            json.dump({
                "access_token": self.access_token,
                "open_id": self.open_id,
            }, f)
    
    def is_authenticated(self) -> bool:
        return self.access_token is not None
    
    async def init_upload(
        self,
        video_path: str,
        title: str,
        privacy: str = "PUBLIC_TO_EVERYONE",
        disable_duet: bool = False,
        disable_stitch: bool = False,
        disable_comment: bool = False,
    ) -> dict:
        """TikTok'a video yükleme başlat
        
        Args:
            privacy: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, 
                     FOLLOWER_OF_CREATOR, SELF_ONLY
        """
        if not self.is_authenticated():
            return {"error": "TikTok kimlik doğrulaması gerekli"}
        
        file_size = os.path.getsize(video_path)
        
        # 1. Upload başlat
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        
        init_body = {
            "post_info": {
                "title": title[:150],
                "privacy_level": privacy,
                "disable_duet": disable_duet,
                "disable_stitch": disable_stitch,
                "disable_comment": disable_comment,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": min(file_size, 10 * 1024 * 1024),
                "total_chunk_count": max(1, file_size // (10 * 1024 * 1024)),
            }
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/post/publish/inbox/video/init/",
                headers=headers,
                json=init_body,
                timeout=30,
            )
            
            if resp.status_code != 200:
                return {"error": f"TikTok API hata: {resp.text}"}
            
            data = resp.json()
            upload_url = data.get("data", {}).get("upload_url")
            publish_id = data.get("data", {}).get("publish_id")
            
            # 2. Video yükle
            with open(video_path, "rb") as f:
                video_data = f.read()
            
            upload_resp = await client.put(
                upload_url,
                content=video_data,
                headers={
                    "Content-Range": f"bytes 0-{file_size-1}/{file_size}",
                    "Content-Type": "video/mp4",
                },
                timeout=120,
            )
            
            return {
                "publish_id": publish_id,
                "status": "uploaded",
                "platform": "tiktok",
            }
    
    def check_status(self) -> dict:
        """TikTok bağlantı durumunu kontrol et"""
        return {
            "authenticated": self.is_authenticated(),
            "open_id": self.open_id,
        }
