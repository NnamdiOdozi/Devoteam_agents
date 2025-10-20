#!/usr/bin/env python3

import os
from pathlib import Path
from typing import Union, Tuple
import PyPDF2


class DocumentLoader:
    """Utility class for loading different document types."""
    
    @staticmethod
    def load_document(file_path: str) -> Tuple[bytes, str]:
        """
        Load a document and return its content and media type.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Tuple of (content_bytes, media_type)
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file type is not supported or PDF has >100 pages
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        file_extension = Path(file_path).suffix.lower()
        
        if file_extension == '.pdf':
            # Check PDF page count before loading
            page_count = DocumentLoader._get_pdf_page_count(file_path)
            if page_count > 100:
                raise ValueError(f"PDF has {page_count} pages, maximum allowed is 100 pages")
            return DocumentLoader._load_pdf(file_path)
        elif file_extension == '.txt':
            return DocumentLoader._load_txt(file_path)
        elif file_extension == '.docx':
            return DocumentLoader._load_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")
    
    @staticmethod
    def _get_pdf_page_count(file_path: str) -> int:
        """Get the number of pages in a PDF file."""
        try:
            with open(file_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                return len(pdf_reader.pages)
        except Exception as e:
            # If we can't determine page count, assume it's valid
            print(f"Warning: Could not determine page count for {file_path}: {e}")
            return 1
    
    @staticmethod
    def _load_pdf(file_path: str) -> Tuple[bytes, str]:
        """Load PDF file as bytes."""
        with open(file_path, "rb") as file:
            return file.read(), "application/pdf"
    
    @staticmethod
    def _load_txt(file_path: str) -> Tuple[bytes, str]:
        """Load text file and convert to bytes."""
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            return content.encode("utf-8"), "text/plain"
    
    @staticmethod
    def _load_docx(file_path: str) -> Tuple[bytes, str]:
        """Load DOCX file as bytes."""
        with open(file_path, "rb") as file:
            return file.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    
    @staticmethod
    def get_document_name(file_path: str) -> str:
        """Extract a clean document name from the file path."""
        return Path(file_path).stem
    
    @staticmethod
    def get_document_type(file_path: str) -> str:
        """Determine document type based on directory structure."""
        path_parts = Path(file_path).parts
        
        if "Legislations" in path_parts:
            return "legislation"
        elif "Guidlines" in path_parts:
            return "guidelines"
        elif "News" in path_parts:
            return "news"
        else:
            return "unknown"
