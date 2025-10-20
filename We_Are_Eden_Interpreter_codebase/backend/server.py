#!/usr/bin/env python3

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, AsyncGenerator

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.assessor import PolicyAssessor
from backend.models import PolicyAssessmentResult

app = FastAPI(title="Policy Assessment Tool")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Initialize the policy assessor
assessor = PolicyAssessor()

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main frontend HTML page."""
    frontend_path = Path("frontend/index.html")
    if not frontend_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    
    with open(frontend_path, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/api/categories")
async def get_categories() -> Dict[str, Any]:
    """Get available categories and their reference documents."""
    categories_data = {}
    
    for category, docs in assessor.document_categories.items():
        categories_data[category] = {
            "legislation": {
                "count": len(docs.get("legislation", [])),
                "documents": [Path(doc).name for doc in docs.get("legislation", [])]
            },
            "guidelines": {
                "count": len(docs.get("guidelines", [])),
                "documents": [Path(doc).name for doc in docs.get("guidelines", [])]
            },
            "news": {
                "count": len(docs.get("news", [])),
                "documents": [Path(doc).name for doc in docs.get("news", [])]
            }
        }
    
    return {
        "categories": categories_data,
        "total_categories": len(categories_data)
    }

@app.post("/api/assess")
async def assess_policy_stream(
    file: UploadFile = File(...),
    category: str = Form(...)
):
    """
    Assess a policy document against reference documents with SSE progress updates.
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Validate category
    if category not in assessor.document_categories:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid category. Must be one of: {list(assessor.document_categories.keys())}"
        )
    
    # Save uploaded file temporarily
    temp_file_path = f"temp_{file.filename}"
    try:
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        async def generate_progress():
            try:
                async for event in assessor.assess_policy_with_progress(temp_file_path, category):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                error_event = {
                    "type": "error",
                    "message": f"Assessment failed: {str(e)}"
                }
                yield f"data: {json.dumps(error_event)}\n\n"
            finally:
                # Clean up temporary file
                if Path(temp_file_path).exists():
                    Path(temp_file_path).unlink()
        
        return StreamingResponse(
            generate_progress(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        # Clean up if error before streaming starts
        if Path(temp_file_path).exists():
            Path(temp_file_path).unlink()
        raise HTTPException(status_code=500, detail=f"Assessment failed: {str(e)}")

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "Policy Assessment Tool"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="0.0.0.0", port=8000, reload=True)
