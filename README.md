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
| `GET /api/topics/{slug}/tweets` | Top tweets for a topic |
| `POST /api/topics/{slug}/tweets/refresh` | Clear cache for topic tweets |

## X API integration (Community Feed / Top Tweets)

To enable the Community Feed widget on each Topic page (shows recent top tweets on the topic), set one of these environment variables before starting the backend. You can place them in a `.env` at the project root (preferred) or in `backend/.env`:

- `X_BEARER_TOKEN` (preferred)
- `TWITTER_BEARER_TOKEN` (fallback)

The token must have access to the Recent Search endpoint. The backend uses the Recent Search API with relevancy sorting and filters out retweets/replies for concise results.

Caching and rate limiting (in-memory):
- `TWEETS_CACHE_TTL` (seconds, default 90) — cache TTL per topic query
- `TWEETS_RATE_WINDOW` (seconds, default 60) — rate-limit window
- `TWEETS_RATE_MAX` (integer, default 20) — max requests per window (global)

Notes:
- Results are cached per normalized query and `max_results`.
- If cache is warm, rate limiting is bypassed for that key to reduce external calls.

### How “Top Tweets” are determined

- Query construction: the topic slug is converted to a quoted phrase, underscores/hyphens → spaces, and filtered with `-is:retweet -is:reply lang:en`.
- Candidate pool: we fetch from BOTH X Recent Search (`/2/tweets/search/recent`) and Full-Archive Search (`/2/tweets/search/all`) when permitted by your token, each with `sort_order=relevancy`. Results are combined and deduplicated by tweet ID (recent entry preferred when overlapping). If Full-Archive is not permitted, only recent results are considered.
- Engagement scoring: each candidate is scored and re-ranked server-side using public metrics and author size normalization:
  - raw_engagement = likes + 2×retweets + 1.5×quotes + 0.5×replies
  - normalization = max(50, followers_count)^0.7
  - score = raw_engagement / normalization
- Final list: candidates are sorted by `score` descending; the top `max_results` are returned to the client.
- Caching and refresh: results are cached in-memory per topic phrase and `max_results` for `TWEETS_CACHE_TTL` seconds. Use `POST /api/topics/{slug}/tweets/refresh` (or the ↻ button in the UI) to clear the cache and refetch fresh results.
- UI: the left rail shows a compact, sticky “Top Tweets” widget with ranked numbers; the top three items are visually highlighted. Items link directly to the tweet on X.
