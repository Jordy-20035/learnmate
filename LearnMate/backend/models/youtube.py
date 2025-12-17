# backend/models/youtube.py
import re
import logging
import os
import tempfile
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

    def _get_youtube_captions(self, video_url: str) -> dict | None:
        """Try to fetch existing YouTube captions/subtitles"""
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["ru", "en", "uk"],  # Preferred languages
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                
                # Check for subtitles (manual or auto-generated)
                subtitles = info.get("subtitles", {})
                auto_captions = info.get("automatic_captions", {})
                
                # Priority: ru manual > ru auto > en manual > en auto
                for lang in ["ru", "en", "uk"]:
                    # Check manual subtitles first
                    if lang in subtitles:
                        for fmt in subtitles[lang]:
                            if fmt.get("ext") in ["vtt", "srv1", "srv2", "srv3", "ttml", "json3"]:
                                caption_url = fmt.get("url")
                                if caption_url:
                                    logger.info(f"Found manual {lang} subtitles")
                                    return self._download_and_parse_captions(caption_url, lang)
                    
                    # Check auto-generated captions
                    if lang in auto_captions:
                        for fmt in auto_captions[lang]:
                            if fmt.get("ext") in ["vtt", "srv1", "srv2", "srv3", "ttml", "json3"]:
                                caption_url = fmt.get("url")
                                if caption_url:
                                    logger.info(f"Found auto-generated {lang} captions")
                                    return self._download_and_parse_captions(caption_url, lang)
                
                logger.info("No suitable captions found")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to fetch YouTube captions: {e}")
            return None

    def _download_and_parse_captions(self, caption_url: str, lang: str) -> dict | None:
        """Download and parse caption file"""
        try:
            import urllib.request
            
            req = urllib.request.Request(
                caption_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode("utf-8")
            
            # Parse VTT/SRV format - extract text only
            lines = content.split("\n")
            text_lines = []
            
            for line in lines:
                line = line.strip()
                # Skip timing lines, headers, and empty lines
                if not line:
                    continue
                if line.startswith("WEBVTT"):
                    continue
                if "-->" in line:  # Timing line
                    continue
                if re.match(r"^\d+$", line):  # Line numbers
                    continue
                if line.startswith("Kind:") or line.startswith("Language:"):
                    continue
                # Remove HTML tags like <c>, </c>, <00:00:00.000>
                clean_line = re.sub(r"<[^>]+>", "", line)
                if clean_line.strip():
                    text_lines.append(clean_line.strip())
            
            # Remove duplicates while preserving order
            seen = set()
            unique_lines = []
            for line in text_lines:
                if line not in seen:
                    seen.add(line)
                    unique_lines.append(line)
            
            text = " ".join(unique_lines)
            
            if text and len(text) > 50:
                logger.info(f"✅ Extracted {len(text)} characters from YouTube captions")
                return {
                    "status": "success",
                    "text": text,
                    "language": lang,
                    "source": "youtube_captions"
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to parse captions: {e}")
            return None

    def get_transcript(self, video_url: str) -> dict:
        """Get transcript - tries YouTube captions first, falls back to Whisper"""
        audio_path = None
        try:
            video_id = self.extract_video_id(video_url)
            logger.info(f"Processing YouTube video: {video_id}")

            # Method 1: Try to get existing YouTube captions (faster, more reliable)
            logger.info("🔍 Checking for YouTube captions...")
            captions = self._get_youtube_captions(video_url)
            if captions:
                logger.info("✅ Using YouTube captions")
                return captions

            # Method 2: Fall back to audio download + Whisper
            logger.info("📥 No captions found, downloading audio for Whisper...")
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
                "source": "whisper"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Transcription failed: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

        finally:
            if audio_path and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                    # Also try to remove the temp directory
                    temp_dir = os.path.dirname(audio_path)
                    if temp_dir and os.path.exists(temp_dir):
                        import shutil
                        shutil.rmtree(temp_dir, ignore_errors=True)
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
                # Anti-403 options
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-us,en;q=0.5",
                    "Sec-Fetch-Mode": "navigate",
                },
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"],
                    }
                },
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
