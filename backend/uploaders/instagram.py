"""
ClipEngine - Instagram Reels Uploader
Meta Graph API ile Reels upload (Business/Creator hesap gerektirir)
"""

import httpx
import json
import os
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent
IG_CONFIG_PATH = BASE_DIR / "credentials" / "instagram_config.json"


class InstagramUploader:
    """Instagram Graph API ile Reels yükleme"""
    
    BASE_URL = "https://graph.facebook.com/v21.0"
    
    def __init__(self):
        self.access_token = None
        self.ig_user_id = None
        self._load_config()
    
    def _load_config(self):
        if IG_CONFIG_PATH.exists():
            with open(IG_CONFIG_PATH) as f:
                config = json.load(f)
                self.access_token = config.get("access_token")
                self.ig_user_id = config.get("ig_user_id")
    
    def _save_config(self):
        os.makedirs(IG_CONFIG_PATH.parent, exist_ok=True)
        with open(IG_CONFIG_PATH, "w") as f:
            json.dump({
                "access_token": self.access_token,
                "ig_user_id": self.ig_user_id,
            }, f)
    
    def is_authenticated(self) -> bool:
        return self.access_token is not None and self.ig_user_id is not None
    
    async def upload_reel(
        self,
        video_url: str,
        caption: str,
        share_to_feed: bool = True,
    ) -> dict:
        """Instagram Reels yükle
        
        NOT: Instagram API doğrudan dosya upload desteklemez,
        video'nun bir URL'den erişilebilir olması gerekir.
        Bunun için videonuzu önce bir hosting'e (R2, S3 vb.) yükleyebilirsiniz.
        
        Args:
            video_url: Videonun public URL'i
            caption: Reels açıklaması
            share_to_feed: Ana beslemeye de paylaş
        """
        if not self.is_authenticated():
            return {"error": "Instagram kimlik doğrulaması gerekli"}
        
        async with httpx.AsyncClient() as client:
            # 1. Container oluştur
            container_resp = await client.post(
                f"{self.BASE_URL}/{self.ig_user_id}/media",
                params={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                    "share_to_feed": str(share_to_feed).lower(),
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            
            if container_resp.status_code != 200:
                return {"error": f"Container oluşturulamadı: {container_resp.text}"}
            
            container_id = container_resp.json()["id"]
            
            # 2. İşlenme durumunu kontrol et
            for _ in range(30):  # Max 5 dakika bekle
                status_resp = await client.get(
                    f"{self.BASE_URL}/{container_id}",
                    params={
                        "fields": "status_code",
                        "access_token": self.access_token,
                    }
                )
                status = status_resp.json().get("status_code")
                
                if status == "FINISHED":
                    break
                elif status == "ERROR":
                    return {"error": "Instagram video işleme hatası"}
                
                time.sleep(10)
            
            # 3. Yayınla
            publish_resp = await client.post(
                f"{self.BASE_URL}/{self.ig_user_id}/media_publish",
                params={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            
            if publish_resp.status_code != 200:
                return {"error": f"Yayınlama hatası: {publish_resp.text}"}
            
            media_id = publish_resp.json()["id"]
            
            return {
                "media_id": media_id,
                "status": "published",
                "platform": "instagram",
            }
    
    def check_status(self) -> dict:
        return {
            "authenticated": self.is_authenticated(),
            "ig_user_id": self.ig_user_id,
        }
