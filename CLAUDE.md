# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

10xGrokipedia is an AI-powered encyclopedia with a Wikipedia-like interface. It's a monorepo containing:

- **frontend/**: React + TypeScript (Vite)
- **backend/**: FastAPI (Python)

## Development Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
Backend runs on http://localhost:8000

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend runs on http://localhost:5173

### Run Both (from root)
```bash
# Terminal 1
cd backend && uvicorn main:app --reload

# Terminal 2
cd frontend && npm run dev
```

## Architecture

### Routes
- `/` - Home page with search bar
- `/page/{topic}` - Topic page displaying title and description

### API Endpoints
- `GET /api/topics` - List all topics
- `GET /api/topics/search?q=query` - Search topics
- `GET /api/topics/{topic_slug}` - Get topic by slug

### Data
Topic data is stored in `backend/temp_data.json`. Each topic has:
- `topic`: URL slug
- `title`: Display name
- `description`: Content (markdown supported)

## Key Files
- `backend/main.py` - FastAPI app with all endpoints
- `frontend/src/api.ts` - API client functions
- `frontend/src/pages/Home.tsx` - Search page component
- `frontend/src/pages/TopicPage.tsx` - Topic display component
