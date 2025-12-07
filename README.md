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
| `GET /api/topics/{slug}/tweets/summary` | Grok-generated 2–3 bullet summary of top tweets |
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
- Candidate pool: the backend uses X Full-Archive Search (`/2/tweets/search/all`) with `sort_order=relevancy` to fetch a pool of candidates (default ~50). If your token is not entitled for Full-Archive (401/403), it falls back automatically to Recent Search (`/2/tweets/search/recent`) with the same parameters.
- Engagement scoring: each candidate is scored and re-ranked server-side using public metrics and author size normalization:
  - raw_engagement = likes + 2×retweets + 1.5×quotes + 0.5×replies
  - normalization = max(50, followers_count)^0.7
  - verified boost: if the author is verified on X, a modest multiplicative boost is applied (default 1.1×)
  - score = (raw_engagement / normalization) × verified_boost
- Final list: candidates are sorted by `score` descending; the top `max_results` are returned to the client.
- "Trending" flag: a tweet is marked as trending when it is among the top `TWEETS_TRENDING_TOP_K` ranked items and was created within `TWEETS_TRENDING_HOURS` hours (defaults: top 3 within 7 days / 168h). The UI displays a small “Trending” badge for these tweets.
  - Preview override (optional): to force-show trending badges for quick UI reviews, set either
    - `TWEETS_TRENDING_PREVIEW_TOP_K=5` (marks ranks 1–5 as trending), or
    - `TWEETS_TRENDING_PREVIEW_RANKS=1,5` (marks specific ranks, 1-based) regardless of recency.
- Caching and refresh: results are cached in-memory per topic phrase and `max_results` for `TWEETS_CACHE_TTL` seconds. Use `POST /api/topics/{slug}/tweets/refresh` (or the ↻ button in the UI) to clear the cache and refetch fresh results.
- UI: the left rail shows a compact, sticky “Top Tweets” widget with ranked numbers; the top three items are visually highlighted. Items link directly to the tweet on X.
  - Verified authors display a small blue check next to their display name.

Reliability and rate limits:
- The service uses an in-memory single-flight mechanism to prevent duplicate upstream calls for the same topic while a fetch is in flight.
- If the upstream X API returns `429 Too Many Requests`, the backend serves the last cached result (if available) instead of failing the request.

### Grok Summary of Top Tweets

- Endpoint: `GET /api/topics/{slug}/tweets/summary?max_results=10`
- The backend generates 2–3 concise bullet points summarizing the highest-ranked tweets for the topic using the Grok API.
- Inputs to Grok: the current topic phrase and the top 3–5 tweets (by engagement score) including basic metrics. The prompt emphasizes prioritizing the “top of the top” tweets, neutral tone, and no links/hashtags.
- Caching: summaries are cached in-memory for `TWEETS_SUMMARY_TTL` seconds (default 600s). The `POST /tweets/refresh` endpoint also clears the summary cache for that topic.
- Env vars:
  - `GROK_API` (required) — Grok API key (root `.env` is supported)
  - `GROK_API_BASE` (optional, default `https://api.x.ai/v1`)
  - `GROK_MODEL` (optional, default `grok-2-latest`)
  - `TWEETS_SUMMARY_TTL` (optional, seconds, default `600`)
  - `TWEETS_TRENDING_HOURS` (optional, hours, default `168`)
  - `TWEETS_TRENDING_TOP_K` (optional, integer, default `3`)
  - `TWEETS_VERIFIED_BOOST` (optional, float multiplier, default `1.1`) — modest lift for verified authors in ranking
#### Trending flag details

- Computation: trending = ranked_index < `TWEETS_TRENDING_TOP_K` AND created_at within `TWEETS_TRENDING_HOURS`.
- Defaults: highlights a small number of highly-ranked, recent tweets (top 3 within 7 days) to keep the UI informative but not overwhelming.
- Preview overrides (optional):
  - `TWEETS_TRENDING_PREVIEW_TOP_K=5` (forces trending for ranks 1–5)
  - `TWEETS_TRENDING_PREVIEW_RANKS=1,5` (forces specific ranks, 1-based)
