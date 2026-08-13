import io
import os
import re
from typing import List

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader

load_dotenv()

app = FastAPI(title="PDF Notes AI API", version="1.0.0")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_SIZE = 15 * 1024 * 1024
CHUNK_SIZE = 12000
CHUNK_OVERLAP = 500


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read this PDF.") from exc

    pages: List[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")

    text = clean_text("\n\n".join(pages))
    if not text:
        raise HTTPException(
            status_code=422,
            detail="No selectable text was found. This PDF may be scanned/image-only and would need OCR.",
        )
    return text, len(reader.pages)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            natural_break = max(
                text.rfind("\n", start, end),
                text.rfind(". ", start, end),
            )
            if natural_break > start + size // 2:
                end = natural_break + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


async def llm_chat(system_prompt: str, user_prompt: str, max_tokens: int = 1800) -> str:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL")

    if not api_key or not model:
        raise HTTPException(
            status_code=500,
            detail="LLM_API_KEY and LLM_MODEL must be configured on the backend.",
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider error: {exc.response.text[:500]}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not contact the configured LLM provider.",
        ) from exc


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "pdf-notes-ai"}


@app.post("/api/notes")
async def create_notes(file: UploadFile = File(...)):
    filename = file.filename or "document.pdf"
    if (
        file.content_type not in {"application/pdf", "application/x-pdf"}
        and not filename.lower().endswith(".pdf")
    ):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="PDF is too large. Maximum size is 15 MB.")

    text, page_count = extract_pdf_text(data)
    chunks = chunk_text(text)
    section_notes: List[str] = []

    system = (
        "You are an expert academic note-taking assistant. Create accurate compact notes "
        "only from the supplied source. Never invent facts."
    )

    for index, chunk in enumerate(chunks, 1):
        prompt = f"""Create concise Markdown study notes for section {index} of {len(chunks)}.
Preserve key concepts, definitions, formulas, names, dates, examples, steps and important numbers.
Do not add outside knowledge.

SOURCE:
{chunk}"""
        section_notes.append(await llm_chat(system, prompt, 1400))

    combined = "\n\n".join(section_notes)
    final_prompt = f"""Turn these section notes into one polished set of study notes.
Return Markdown with this structure:
# Title
## Executive Summary
4-7 bullets.
## Key Concepts
Use useful topic headings and bullets.
## Important Definitions
Write "None explicitly stated." if none.
## Important Facts, Numbers & Formulas
Write "None explicitly stated." if none.
## Quick Revision
8-15 short bullets.
## Questions to Test Yourself
5-10 answerable questions.

Merge duplicates and do not invent information.

SECTION NOTES:
{combined}"""

    notes = await llm_chat(system, final_prompt, 2800)

    return {
        "filename": filename,
        "pages": page_count,
        "characters_extracted": len(text),
        "chunks_processed": len(chunks),
        "notes": notes,
    }
