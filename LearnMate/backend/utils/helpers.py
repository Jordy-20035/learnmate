import os
import io
import logging
from typing import Union
import nbformat


logger = logging.getLogger(__name__)

class Helpers:
    @staticmethod
    def get_file_extension(filename: str) -> str:
        return os.path.splitext(filename)[1].lower()

    @staticmethod
    def create_file_response(content: Union[str, bytes], 
                           media_type: str, 
                           filename: str) -> io.BytesIO:
        if isinstance(content, str):
            content = content.encode('utf-8')
            
        file_obj = io.BytesIO(content)
        file_obj.seek(0)
        return file_obj
    
    # @staticmethod
    # def create_notebook_with_explanation(code: str, explanation: str, filename: str = "code_analysis.ipynb") -> bytes:
    #     nb = nbformat.v4.new_notebook()
    #     # Add code cell
    #     nb.cells.append(nbformat.v4.new_code_cell(code))
    #     # Add markdown cell with explanation
    #     nb.cells.append(nbformat.v4.new_markdown_cell(explanation))
    #     # Serialize notebook to bytes
    #     return nbformat.writes(nb).encode("utf-8")