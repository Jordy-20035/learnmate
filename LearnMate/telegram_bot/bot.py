import os
import tempfile
import logging
import requests
from tempfile import NamedTemporaryFile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from dotenv import load_dotenv
from io import BytesIO
from telegram import ReplyKeyboardMarkup
import re
import traceback


# Configuration
# Load .env from project root (go up one level from bot/)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

# Now access variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

BACKEND_URL = os.getenv("BACKEND_URL")
MAX_MESSAGE_LENGTH = 4000  # Telegram message length limit


YOUTUBE_URL_REGEX = re.compile(
    r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+'
)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📄 Translate Document", callback_data="translate")],
        [InlineKeyboardButton("💻 Analyze Code", callback_data="analyze")],
        [InlineKeyboardButton("🎬 Transcribe YouTube", callback_data="transcribe")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_analysis_type_keyboard():
    """Keyboard for choosing analysis type"""
    keyboard = [
        [InlineKeyboardButton("🔍 Explain Code", callback_data="analyze_explain")],
        [InlineKeyboardButton("🚀 Implementation Guide", callback_data="analyze_implement")],
        [InlineKeyboardButton("📋 Code Review", callback_data="analyze_review")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


class BotHandler:
    def __init__(self):
        self.supported_extensions = {".pdf", ".docx", ".pptx", ".txt", ".ipynb", ".py"}
        self.youtube_domains = {"youtube.com", "youtu.be"}


    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        welcome_text = (
            "🤖 Welcome to LearnMate PRO!\n\n"
            "Choose an action:\n"
            "• Translate documents (PDF, DOCX, PPTX, TXT, IPYNB)\n"
            "• Analyze and explain code\n"
            "• Transcribe YouTube videos\n"
        )
        reply_markup = get_main_menu_keyboard()
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)


    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show main menu anytime"""
        await update.message.reply_text(
            "🔹 Main Menu: Choose an action",
            reply_markup=get_main_menu_keyboard()
        )


    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard button presses"""
        query = update.callback_query
        await query.answer()
        
        action = query.data
        
        if action == "menu":
            # Return to main menu
            await query.edit_message_text(
                "🔹 Main Menu: Choose an action",
                reply_markup=get_main_menu_keyboard()
            )
            return
                # Handle analysis type selection
        if action.startswith("analyze_"):
            analysis_type = action.replace("analyze_", "")
            context.user_data["analysis_type"] = analysis_type
            await query.edit_message_text(
                f"💻 Analysis mode: {analysis_type.replace('_', ' ').title()}\n\n"
                "Send me your code file (.py, .ipynb, .txt) to analyze:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Change Analysis Type", callback_data="analyze")]
                ])
            )
            return
        
        # Store selected action in user context
        context.user_data["action"] = action

                # Prepare response based on action
        if action == "analyze":
            # Show analysis type selection
            await query.edit_message_text(
                "🔍 Choose analysis type:",
                reply_markup=get_analysis_type_keyboard()
            )
            return
        
        # Prepare response based on action
        action_texts = {
            "translate": "📄 Send me the document you want to translate",
            "transcribe": "🎬 Send me a YouTube video URL to transcribe"
        }
        
        # Add back to menu button
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
        ])
        
        await query.edit_message_text(
            text=action_texts.get(action, "Please send me your file or URL"),
            reply_markup=reply_markup
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Route messages to appropriate handler based on content type and user's selected action."""
        action = context.user_data.get("action")

        if not action and update.message.text:
            if YOUTUBE_URL_REGEX.search(update.message.text):
                context.user_data["action"] = "transcribe"
                await self.handle_youtube_link(update, context)
                return
            else:
                await update.message.reply_text(
                    "⚠️ Please choose an action first!",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
        if not action:
            await update.message.reply_text(
                "⚠️ Please choose an action first!",
                reply_markup=get_main_menu_keyboard()
            )
            return            

        try:
            if update.message.document:
                await self.handle_document(update, context)
            elif update.message.text:
                if action == "transcribe":
                    await self.handle_youtube_link(update, context)
                else:
                    await update.message.reply_text(
                        f"⚠️ For {action}, please send a file",
                        reply_markup=get_main_menu_keyboard()
                    )
            else:
                await update.message.reply_text(
                    "⚠️ Unsupported message type",
                    reply_markup=get_main_menu_keyboard()
                )

        except Exception as e:
            logger.error(f"Error during '{action}' processing: {e}")
            await update.message.reply_text(
                f"⚠️ An error occurred during {action}. Please try again.",
                reply_markup=get_main_menu_keyboard()
            )
            context.user_data.pop("action", None)
            context.user_data.pop("analysis_type", None)


    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        document = update.message.document
        filename = document.file_name
        file_ext = os.path.splitext(filename)[1].lower()
        
        SUPPORTED_TYPES = {
            '.pdf': 'PDF Document',
            '.docx': 'Word Document',
            '.pptx': 'PowerPoint',
            '.ipynb': 'Jupyter Notebook',
            '.txt': 'Text File',
            '.py': 'Python Script'
        }
        
        if file_ext not in SUPPORTED_TYPES:
            types_list = "\n".join([f"- {desc} ({ext})" for ext, desc in SUPPORTED_TYPES.items()])
            await update.message.reply_text(f"❌ Unsupported file type. Supported types:\n{types_list}")
            return

        try:
            action = context.user_data.get("action", "")
            if not action:
                await update.message.reply_text("❌ Please select an action first using /start")
                return


            # Special handling for code analysis
            if action == "analyze":
                analysis_type = context.user_data.get("analysis_type", "explain")
                await self._handle_code_analysis(update, context, document, filename, file_ext, analysis_type)
            else:
                # Handle translation
                await self._handle_translation(update, context, document, filename, file_ext)

        except Exception as e:
            logger.error(f"Document handling failed: {str(e)}")
            logger.error(traceback.format_exc())
            await update.message.reply_text("⚠️ An unexpected error occurred")

    async def _handle_code_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                  document, filename: str, file_ext: str, analysis_type: str):
        """Handle code analysis requests"""
        try:
            # Get analysis type display name
            analysis_names = {
                "explain": "Explanation",
                "implement": "Implementation Guide", 
                "review": "Code Review"
            }
            
            analysis_name = analysis_names.get(analysis_type, "Analysis")
            
            # Special message for notebooks
            if file_ext == '.ipynb':
                await update.message.reply_text(
                    f"📓 Processing Jupyter notebook for {analysis_name}...\n"
                    "⏳ This may take 1-2 minutes for complex notebooks\n"
                    "💡 Tip: For faster analysis, consider exporting as .py file"
                )
                timeout = 120
            else:
                await update.message.reply_text(f"💻 Analyzing code for {analysis_name}...")
                timeout = 90

            # Check backend health
            try:
                health_check = requests.get(f"{BACKEND_URL}/health", timeout=5)
                if health_check.status_code != 200:
                    raise ConnectionError("Backend not healthy")
            except requests.exceptions.RequestException:
                raise ConnectionError("Could not reach backend")

            # Download file
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()

            # Prepare request
            files = {'file': (filename, BytesIO(file_content))}
            data = {'analysis_type': analysis_type}

            # Send to backend
            response = requests.post(
                f"{BACKEND_URL}/analyze_code",
                files=files,
                data=data,
                timeout=timeout
            )

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('status') == 'success':
                    await self._handle_analysis_response(update, response_data, analysis_name)
                else:
                    error_msg = response_data.get('error', 'Unknown error')
                    await update.message.reply_text(f"❌ Analysis error: {error_msg}")
            else:
                await update.message.reply_text(f"❌ Backend error (status {response.status_code})")

        except requests.Timeout:
            await update.message.reply_text(
                "⌛ Analysis timed out. Try these solutions:\n"
                "1. Export notebook as .py file and try again\n"  
                "2. Split code into smaller files\n"
                "3. Try again later",
                reply_markup=get_main_menu_keyboard()
            )
        except requests.exceptions.ConnectionError:
            await update.message.reply_text("🔌 Backend service unavailable. Please try again later.")
        except Exception as e:
            logger.error(f"Code analysis failed: {str(e)}")
            logger.error(traceback.format_exc())
            await update.message.reply_text("⚠️ An error occurred during code analysis")


    async def _handle_translation(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                document, filename: str, file_ext: str):
        """Handle translation requests"""
        try:
            await update.message.reply_text("🌍 Translating document...")

            # Check backend health
            try:
                health_check = requests.get(f"{BACKEND_URL}/health", timeout=5)
                if health_check.status_code != 200:
                    raise ConnectionError("Backend not healthy")
            except requests.exceptions.RequestException:
                raise ConnectionError("Could not reach backend")

            # Download file
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()

            # Send to backend
            files = {'file': (filename, BytesIO(file_content))}
            response = requests.post(
                f"{BACKEND_URL}/translate_file",
                files=files,
                timeout=60
            )

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('status') == 'success':
                    await self._handle_translation_response(update, response_data)
                else:
                    error_msg = response_data.get('error', 'Unknown error')
                    await update.message.reply_text(f"❌ Translation error: {error_msg}")
            else:
                await update.message.reply_text(f"❌ Backend error (status {response.status_code})")

        except requests.Timeout:
            await update.message.reply_text("⌛ Translation timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            await update.message.reply_text("🔌 Backend service unavailable. Please try again later.")
        except Exception as e:
            logger.error(f"Translation failed: {str(e)}")
            await update.message.reply_text("⚠️ An error occurred during translation")

        
    async def _handle_analysis_response(self, update: Update, response_data: dict, analysis_name: str):
        """Handle successful code analysis response"""
        try:
            explanation = response_data.get('explanation', '')
            filename = response_data.get('filename', 'code.py')

            if not explanation:
                await update.message.reply_text("❌ No analysis generated")
                return

            # Escape HTML special characters
            import html
            safe_explanation = html.escape(explanation)

            # Format with HTML instead of Markdown
            response_text = (
                f"<b>🔍 {analysis_name} of {filename}</b>\n\n"
                f"<pre>{safe_explanation}</pre>\n\n"
                "<b>💡 Analysis completed!</b>"
            )

            # Telegram message limit check
            if len(response_text) > 4000:
                from tempfile import NamedTemporaryFile
                import os

                with NamedTemporaryFile(mode='w', suffix='.txt', encoding='utf-8', delete=False) as f:
                    f.write(explanation)
                    temp_path = f.name

                try:
                    with open(temp_path, 'rb') as file_obj:
                        await update.message.reply_document(
                            document=file_obj,
                            filename=f"analysis_{filename}.txt",
                            caption=f"{analysis_name} completed ✅"
                        )
                finally:
                    os.unlink(temp_path)
            else:
                await update.message.reply_text(
                    response_text,
                    parse_mode="HTML"
                )

            # Safely clear context
            context = update.message.bot.get_context() if hasattr(update.message, "bot") else None
            if context:
                context.user_data.pop("action", None)
                context.user_data.pop("analysis_type", None)

            await update.message.reply_text(
                "✅ Analysis completed! Choose another action:",
                reply_markup=get_main_menu_keyboard()
            )

        except Exception as e:
            logger.error(f"Error handling analysis response: {str(e)}", exc_info=True)
            await update.message.reply_text(
                "⚠️ Failed to process analysis results",
                reply_markup=get_main_menu_keyboard()
            )    



    async def _handle_translation_response(self, update: Update, response_data: dict):
        """Handle successful translation response"""
        try:
            translated_content = response_data.get('translated_text', '')
            filename = response_data.get('filename', 'translated.txt')
            
            if not translated_content:
                await update.message.reply_text("❌ No translation generated")
                return

            # Create file object
            file_obj = BytesIO(translated_content.encode('utf-8'))
            file_obj.seek(0)
            
            # Send preview and document
            preview = (
                f"📄 Translation ready!\n"
                f"Original: {response_data.get('source_chars', 0)} characters\n"
                f"Download below:"
            )
            await update.message.reply_text(preview)
            
            await update.message.reply_document(
                document=file_obj,
                filename=filename
            )

            # Clear context and show menu
            context = update.message._context
            context.user_data.pop("action", None)
            
            await update.message.reply_text(
                "✅ Translation completed! Choose another action:",
                reply_markup=get_main_menu_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Error handling translation response: {str(e)}")
            await update.message.reply_text(
                "⚠️ Failed to process translation results",
                reply_markup=get_main_menu_keyboard()
            )


    async def handle_youtube_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text or ""
        action = context.user_data.get("action", "")

        if action != "transcribe":
            await update.message.reply_text("❌ Please select transcription mode first using /start")
            return

        match = YOUTUBE_URL_REGEX.search(text)
        if not match:
            await update.message.reply_text("❌ Please send a valid YouTube video URL.")
            return

        video_url = match.group(0)

        try:
            # Check backend health
            try:
                health_check = requests.get(f"{BACKEND_URL}/health", timeout=5)
                if health_check.status_code != 200:
                    raise ConnectionError("Backend not healthy")
            except requests.exceptions.RequestException:
                raise ConnectionError("Could not reach backend")

            await update.message.reply_text("🔄 Fetching and transcribing YouTube video... ⏳ This may take 1-2 minutes.")

            # Send request to backend
            response = requests.post(
                f"{BACKEND_URL}/transcribe_youtube",
                json={"video_url": video_url},
                timeout=600  # 10 minutes timeout for long videos
            )

            if response.status_code == 200:
                # Backend now returns a file directly
                file_content = response.content
                
                # Extract filename from response headers or use default
                filename = "youtube_transcript.txt"
                if 'content-disposition' in response.headers:
                    content_disposition = response.headers['content-disposition']
                    filename_match = re.search(r'filename="([^"]+)"', content_disposition)
                    if filename_match:
                        filename = filename_match.group(1)
                
                # Send the file to user
                file_obj = BytesIO(file_content)
                file_obj.seek(0)
                
                await update.message.reply_document(
                    document=file_obj,
                    filename=filename
                )

                # Clear action and show menu
                context.user_data.pop("action", None)
                
                await update.message.reply_text(
                    "✅ Transcription completed! Choose another action:",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                error_detail = response.json().get('detail', 'Unknown error')
                raise Exception(f"Backend error: {error_detail}")

        except requests.Timeout:
            await update.message.reply_text("⌛ Transcription timed out. The video might be too long. Please try a shorter video.")
        except ConnectionError:
            await update.message.reply_text("🔌 Backend service unavailable. Please try again later.")
        except Exception as e:
            logger.error(f"❌ YouTube transcription failed: {str(e)}")
            await update.message.reply_text(f"⚠️ Failed to transcribe video: {str(e)}")
            await update.message.reply_text(
                "Please try again or choose another action:",
                reply_markup=get_main_menu_keyboard()
            )



def main() -> None:
    """Start the bot."""
    bot_handler = BotHandler()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Register handlers
    app.add_handler(CommandHandler("start", bot_handler.start))
    app.add_handler(CallbackQueryHandler(bot_handler.button_handler))
    
    # Document handler
    app.add_handler(MessageHandler(filters.Document.ALL, bot_handler.handle_document))
    
    # Text message handler - only one needed that routes internally
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        bot_handler.handle_message
    ))
    
    # Menu command
    app.add_handler(CommandHandler("menu", bot_handler.menu))
    
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
