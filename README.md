# 10xGrokipedia

An AI-powered encyclopedia with a Wikipedia-like interface.

## Prerequisites

- Python 3.11+
- Node.js 18+
- npm

## Local Development Setup

### 1. Backend Setup

```bash
cd backend

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn main:app --reload
```

Backend will be available at http://localhost:8000

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

Frontend will be available at http://localhost:5173

## Project Structure

```
10xgrokipedia/
├── backend/
│   ├── main.py           # FastAPI application
│   ├── temp_data.json    # Topic data
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── api.ts        # API client
│   │   ├── pages/        # React pages
│   │   └── App.tsx       # Main app component
│   └── package.json
├── CLAUDE.md
└── README.md
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/topics` | List all topics |
| `GET /api/topics/search?q=query` | Search topics |
| `GET /api/topics/{slug}` | Get topic by slug |
