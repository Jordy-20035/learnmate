# backend/models/youtube.py
import re
import logging
import os
import tempfile
import shutil
from fastapi import HTTPException
from yt_dlp import YoutubeDL
import whisper

logger = logging.getLogger(__name__)

class YouTubeTranscriber:
    def __init__(self):
        try:

            self.model = whisper.load_model("base")
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {str(e)}")
            raise RuntimeError("Could not initialize Whisper model")

    @staticmethod
    def extract_video_id(url: str) -> str:
        """Extract YouTube video ID"""
        patterns = [
            r"(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]+)",
            r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]+)",
            r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]+)",
        ]
        url = url.split("&")[0]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError(f"Invalid YouTube URL: {url}")

    def get_transcript(self, video_url: str) -> dict:
        """Download audio and transcribe using local Whisper"""
        try:
            video_id = self.extract_video_id(video_url)
            logger.info(f"Processing YouTube video: {video_id}")

            audio_path = self._download_audio(video_url)
            logger.info(f"✅ Audio downloaded: {os.path.getsize(audio_path)} bytes")

            logger.info("🎤 Transcribing with Whisper (local)...")
            result = self.model.transcribe(audio_path, language="ru")

            if not result.get("text"):
                raise HTTPException(status_code=500, detail="Whisper returned empty result")

            transcript_text = result["text"].strip()
            logger.info(f"✅ Transcription complete: {len(transcript_text)} characters")

            return {
                "status": "success",
                "text": transcript_text,
                "language": "ru",
                "source": "ai"
            }

        except Exception as e:
            logger.error(f"❌ Transcription failed: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"AI transcription failed: {str(e)}")

        finally:
            if 'audio_path' in locals() and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except Exception as cleanup_err:
                    logger.warning(f"Could not delete temp audio file: {cleanup_err}")

    def _download_audio(self, video_url: str) -> str:
        """Download audio from YouTube as MP3"""
        try:
            tmp_dir = tempfile.mkdtemp()
            output_template = os.path.join(tmp_dir, "%(id)s.%(ext)s")

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "quiet": True,
                "noplaylist": True,
                "no_warnings": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                downloaded_path = ydl.prepare_filename(info)
                audio_path = os.path.splitext(downloaded_path)[0] + ".mp3"

            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                raise HTTPException(status_code=500, detail="Failed to download audio from YouTube")

            return audio_path

        except Exception as e:
            logger.error(f"Audio download failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to download audio from YouTube")
