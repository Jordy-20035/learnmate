# backend/models/translation.py
from dotenv import load_dotenv
load_dotenv()

import logging
import os
from openai import OpenAI

logger = logging.getLogger(__name__)

class TranslationModel:
    def __init__(self):
        # Initialize OpenRouter client
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )

    def translate_text(self, text: str, source_lang: str = "ru", target_lang: str = "en") -> str:
        """Translate text using OpenRouter API"""
        if not text.strip():
            return ""

        try:
            response = self.client.chat.completions.create(
                model="openai/gpt-4o",   # lightweight + fast
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"You are a professional translator. Translate from {source_lang} to {target_lang}. "
                            f"Do not add extra commentary, only return the translated text."
                        )
                    },
                    {"role": "user", "content": text}
                ],
                temperature=0,
                max_tokens=1000
            )

            translated = response.choices[0].message.content.strip()
            return translated if translated else "⚠️ Translation service unavailable"

        except Exception as e:
            logger.error(f"Translation failed: {str(e)}", exc_info=True)
            return f"⚠️ Translation service unavailable: {str(e)}"
