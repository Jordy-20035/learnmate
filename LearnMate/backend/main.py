from dotenv import load_dotenv
import os


load_dotenv()  

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Response, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
import tempfile
import logging
from models.translation import TranslationModel
from models.code_analysis import CodeAnalysisModel
from models.youtube import YouTubeTranscriber
from utils.file_processing import FileProcessor
from utils.helpers import Helpers
import io
from io import BytesIO
import asyncio
import json
from fastapi.middleware.cors import CORSMiddleware



# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize models
translation_model = TranslationModel()
code_analysis_model = CodeAnalysisModel()
youtube_transcriber = YouTubeTranscriber()
file_processor = FileProcessor()

@app.middleware("http")
async def validate_request(request: Request, call_next):
    try:
        if request.method == "POST" and "file" in request.headers.get("content-type", ""):
            if int(request.headers.get("content-length", 0)) == 0:
                return JSONResponse(
                    {"error": "Empty file content"}, 
                    status_code=400
                )
        return await call_next(request)
    except Exception as e:
        logger.error(f"Middleware error: {str(e)}")
        return JSONResponse(
            {"error": "Request validation failed"}, 
            status_code=500
        )

@app.post("/translate_file")
async def translate_file(file: UploadFile = File(...)):
    try:
        # Verify file content
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file content")
        
        file_stream = BytesIO(content)
        ext = Helpers.get_file_extension(file.filename)
        
        # Process file based on type
        if ext == ".pdf":
            text = file_processor.extract_text_from_pdf(file_stream)
        elif ext == ".docx":
            text = file_processor.extract_text_from_docx(file_stream)
        elif ext == ".pptx":
            text = file_processor.extract_text_from_pptx(file_stream)
        elif ext == ".ipynb":
            text = file_processor.extract_code_from_ipynb(content)
        elif ext == ".txt":
            text = file_processor.process_txt(content)
        else:
            raise HTTPException(400, detail="Unsupported file type")

        if not text.strip():
            raise HTTPException(400, detail="No extractable text")

        # Perform translation
        translated_content = translation_model.translate_text(text)
        
        # Return response with ALL required fields
        return {
            "status": "success",
            "filename": f"translated_{file.filename.split('.')[0]}.txt",
            "translated_text": translated_content,  # Key field the bot expects
            "original_text": text[:500] + ("..." if len(text) > 500 else ""),
            "source_chars": len(text),
            "translated_chars": len(translated_content)
        }
        
    except HTTPException as he:
        raise
    except Exception as e:
        logger.error(f"Translation failed: {str(e)}")
        raise HTTPException(500, detail="File processing failed")




@app.post("/analyze_code")
async def analyze_code(
    file: UploadFile = File(...),
    analysis_type: str = Form("explain")   # new: allow passing analysis type
):
    try:
        logger.info(f"Analyze code endpoint called for file: {file.filename}")

        # Read file content
        content = await file.read()
        ext = file.filename.split('.')[-1].lower()
        logger.info(f"File extension: {ext}, content length: {len(content)}")

        # Handle .ipynb separately
        if ext == "ipynb":
            try:
                nb_json = json.loads(content.decode('utf-8'))
                code_cells = []
                for cell in nb_json.get('cells', []):
                    if cell.get('cell_type') == 'code':
                        code_cells.append(''.join(cell.get('source', [])))
                code = '\n\n'.join(code_cells)
            except Exception as e:
                logger.error(f"Failed to parse notebook: {e}")
                raise HTTPException(400, detail="Invalid Jupyter notebook format")
        else:
            try:
                code = content.decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to decode file: {e}")
                raise HTTPException(400, detail="File decoding error")

        logger.info(f"Extracted code length: {len(code)}")
        logger.info(f"Code sample: {code[:200]}...")

        # Call analysis model
        explanation = code_analysis_model.explain_code(code, analysis_type)
        logger.info(f"Final explanation from model: '{explanation[:200]}...'")

        if not explanation or not explanation.strip():
            logger.error("Empty explanation generated")
            raise HTTPException(500, detail="No analysis generated - empty response")

        return {
            "status": "success",
            "explanation": explanation,
            "filename": file.filename
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Code analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="Code analysis failed")


@app.post("/transcribe_youtube")
async def transcribe_youtube(request: Request):
    try:
        data = await request.json()
        video_url = data.get("video_url")
        if not video_url:
            raise HTTPException(status_code=400, detail="video_url is required")
        
        # Get transcript using AI
        transcript_result = await asyncio.to_thread(
            youtube_transcriber.get_transcript, 
            video_url
        )
        
        # Create a temporary file with the transcript
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', encoding='utf-8', delete=False) as temp_file:
            transcript_text = transcript_result["text"]
            language = transcript_result.get("language", "ru")
            source = transcript_result.get("source", "ai")
            
            # Write transcript to file
            temp_file.write(transcript_text)
            temp_file_path = temp_file.name
        
        # Extract video ID for filename
        try:
            video_id = youtube_transcriber.extract_video_id(video_url)
            filename = f"youtube_transcript_{video_id}.txt"
        except:
            filename = "youtube_transcript.txt"
        
        # Return as file download
        return FileResponse(
            path=temp_file_path,
            filename=filename,
            media_type='text/plain'
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    

@app.get("/health")
async def health_check():
    return {"status": "ok"}