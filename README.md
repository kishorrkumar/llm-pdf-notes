# LLM PDF Notes

Full-stack application that extracts text from PDFs and uses an API-based LLM to generate structured study notes.

## Features
- PDF upload with 15 MB validation
- PDF text extraction using PyPDF
- Automatic chunking for larger documents
- OpenAI-compatible LLM API integration
- Structured Markdown study notes
- Executive summary, key concepts, definitions, facts/formulas, quick revision and self-test questions
- Copy generated notes
- Download notes as Markdown
- FastAPI backend and responsive frontend

## Project structure
```text
llm-pdf-notes/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── README.md
```

## Backend
```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure:
```env
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=your_model_name_here
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Run:
```bash
uvicorn main:app --reload --port 8000
```

## Frontend
```bash
cd frontend
python -m http.server 5173
```
Then open `http://localhost:5173`.

## Production
For Render, use `backend` as the root directory, `pip install -r requirements.txt` as the build command and `uvicorn main:app --host 0.0.0.0 --port $PORT` as the start command.

The frontend defaults to `http://localhost:8000`. For production, set `window.PDF_NOTES_API_URL` to your deployed backend URL and add the frontend domain to `ALLOWED_ORIGINS`.

## PDF support
The current version supports text-based PDFs. Image-only/scanned PDFs need an OCR layer.
