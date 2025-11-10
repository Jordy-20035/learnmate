# backend/models/code_analysis.py
from dotenv import load_dotenv
load_dotenv() 

import logging
import json
import nbformat
from pathlib import Path
import os
from openai import OpenAI 



logger = logging.getLogger(__name__)



class CodeAnalysisModel:
    def __init__(self):
        self.client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY")
        )

    def extract_code_from_notebook(self, notebook_path: str) -> str:
        """Extract code from Jupyter notebook"""
        try:
            with open(notebook_path, 'r', encoding='utf-8') as f:
                notebook = nbformat.read(f, as_version=4)
            
            code_cells = []
            for cell in notebook.cells:
                if cell.cell_type == 'code':
                    code_cells.append(cell.source)
            
            return "\n\n# --- Next Cell ---\n\n".join(code_cells)
        except Exception as e:
            logger.error(f"Failed to read notebook: {str(e)}")
            raise

    def explain_code(self, code: str, analysis_type: str = "explain") -> str:
        """Analyze code using OpenAI API instead of local models"""
        try:
            clean_code = code.strip()
            if len(clean_code) > 2000:
                clean_code = clean_code[:2000] + "\n# ... (code truncated for analysis)"

            prompts = {
                "explain": f"Explain the following Python code:\n\n{clean_code}",
                "implement": f"Write a step-by-step implementation guide for this code:\n\n{clean_code}",
                "review": f"Review the following Python code. List issues, improvements, and best practices:\n\n{clean_code}"
            }

            prompt = prompts.get(analysis_type, prompts["explain"])

            response = self.client.chat.completions.create(
                model="openai/gpt-5-codex",   
                messages=[
                    {"role": "system", "content": "You are a helpful coding tutor for students."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=600
            )

            explanation = response.choices[0].message.content.strip()
            return explanation if explanation else "⚠️ No explanation generated."

        except Exception as e:
            logger.error(f"Code analysis failed: {str(e)}", exc_info=True)
            return f"⚠️ Error during code analysis: {str(e)}"

    def process_notebook(self, notebook_path: str, analysis_type: str = "explain") -> str:
        """Process a Jupyter notebook and analyze its code"""
        try:
            code = self.extract_code_from_notebook(notebook_path)
            if not code.strip():
                return "⚠️ No code cells found in the notebook."
            return self.explain_code(code, analysis_type)
        except Exception as e:
            logger.error(f"Notebook processing failed: {str(e)}", exc_info=True)
            return f"⚠️ Failed to process notebook: {str(e)}"
