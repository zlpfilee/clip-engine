"""
ClipEngine - YouTube Shorts Uploader
YouTube Data API v3 ile otomatik Shorts upload
"""

import os
import json
import pickle
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TOKEN_PATH = BASE_DIR / "credentials" / "youtube_token.pickle"
CLIENT_SECRET_PATH = BASE_DIR / "credentials" / "youtube_client_secret.json"


def get_authenticated_service():
    """YouTube API servisi oluştur (OAuth2 ile)"""
    creds = None
    
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                raise FileNotFoundError(
                    f"YouTube client_secret.json bulunamadı: {CLIENT_SECRET_PATH}\n"
                    "Google Cloud Console'dan OAuth2 credentials indirin:\n"
                    "https://console.cloud.google.com/apis/credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_PATH), SCOPES
            )
            creds = flow.run_local_server(port=8090)
        
        os.makedirs(TOKEN_PATH.parent, exist_ok=True)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
    
    return build("youtube", "v3", credentials=creds)


def upload_short(
    video_path: str,
    title: str,
    description: str = "",
    tags: list = None,
    category_id: str = "22",  # People & Blogs
    privacy: str = "public",
    schedule_time: str = None,
) -> dict:
    """YouTube Shorts olarak video yükle
    
    Args:
        video_path: Video dosya yolu
        title: Video başlığı
        description: Video açıklaması
        tags: Etiketler listesi
        category_id: YouTube kategori ID'si
        privacy: public, private, unlisted
        schedule_time: Zamanlanmış yayın (ISO 8601 format) - privacy "private" olmalı
    
    Returns:
        dict: Upload sonucu (video_id, url)
    """
    youtube = get_authenticated_service()
    
    # Shorts için #Shorts etiketi ekle
    if tags is None:
        tags = []
    if "#Shorts" not in tags:
        tags.append("#Shorts")
    
    # Başlığa da #Shorts ekle
    if "#Shorts" not in title:
        title = f"{title} #Shorts"
    
    body = {
        "snippet": {
            "title": title[:100],  # YouTube max 100 karakter
            "description": description[:5000],
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        }
    }
    
    # Zamanlanmış yayın
    if schedule_time:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = schedule_time
    
    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024  # 10MB chunks
    )
    
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )
    
    # Yükleme (progress callback ile)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            print(f"Yükleniyor... {progress}%")
    
    video_id = response["id"]
    
    return {
        "video_id": video_id,
        "url": f"https://youtube.com/shorts/{video_id}",
        "title": title,
        "status": "uploaded",
    }


def check_auth_status() -> dict:
    """YouTube API kimlik doğrulama durumunu kontrol et"""
    try:
        service = get_authenticated_service()
        # Kanal bilgisi al
        response = service.channels().list(
            part="snippet",
            mine=True
        ).execute()
        
        if response.get("items"):
            channel = response["items"][0]
            return {
                "authenticated": True,
                "channel_name": channel["snippet"]["title"],
                "channel_id": channel["id"],
            }
        return {"authenticated": True, "channel_name": "Bilinmiyor"}
    except Exception as e:
        return {
            "authenticated": False,
            "error": str(e),
        }
