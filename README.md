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
│   ├── requirements.txt  # Python dependencies
│   ├── cluster_articles.py        # Article clustering (TF-IDF + union-find)
│   ├── run_llm_contradictions.py  # LLM-based contradiction detection
│   ├── clusters.json              # Cluster output (generated)
│   └── contradictions_llm.json    # Contradictions with offsets (generated)
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
| `GET /api/tweets/search?q=text` | Tweets related to highlighted text |

## Contradiction Pipeline (summary)

- **Clustering (`backend/cluster_articles.py`)**  
  - Builds word- and char-level TF‑IDF vectors on trimmed article text.  
  - Uses similarity gates (title/slug tokens, rare-term overlap) and union-find to form clusters; caps oversized clusters to prevent over-merge.  
  - Output: `clusters.json`.

- **LLM contradiction detection (`backend/run_llm_contradictions.py`)**  
  - For each multi-article cluster, sends articles to X.ai (`grok-4-1-fast-reasoning`) with a prompt demanding exact quotes and JSON pairs.  
  - Parses responses, verifies quotes by locating exact substrings, and attaches character/line offsets.  
  - Output: `contradictions_llm.json`.

- **Frontend consumption**  
  - `frontend/public/contradictions_llm.json` is loaded once on the client.  
  - `TopicPage.tsx` filters contradictions for the current article and injects red underlines; clicking a highlight deep-links to the conflicting line in the other article with auto-scroll and flash.  
  - Toggle shows per-article contradiction count.

### Why this approach
- Clustering narrows pairwise checks so we avoid O(N²) LLM calls across large corpora.  
- Character n-grams improve fuzzy title/entity grouping without hand-coded rules.  
- Exact-quote offsets ensure UI highlights remain precise; pairs that don’t round-trip can be dropped/flagged.

## Contradiction Pipeline (summary)

- **Clustering (`backend/cluster_articles.py`)**  
  - Builds word- and char-level TF‑IDF vectors on trimmed article text.  
  - Uses similarity gates (title/slug tokens, rare-term overlap) and union-find to form clusters; caps oversized clusters to prevent over-merge.  
  - Output: `clusters.json`.

- **LLM contradiction detection (`backend/run_llm_contradictions.py`)**  
  - For each multi-article cluster, sends articles to X.ai (`grok-4-1-fast-reasoning`) with a prompt demanding exact quotes and JSON pairs.  
  - Parses responses, verifies quotes by locating exact substrings, and attaches character/line offsets.  
  - Output: `contradictions_llm.json`.

- **Frontend consumption**  
  - `frontend/public/contradictions_llm.json` is loaded once on the client.  
  - `TopicPage.tsx` filters contradictions for the current article and injects red underlines; clicking a highlight deep-links to the conflicting line in the other article with auto-scroll and flash.  
  - Toggle shows per-article contradiction count.

### Why this approach
- Clustering narrows pairwise checks so we avoid O(N²) LLM calls across large corpora.  
- Character n-grams improve fuzzy title/entity grouping without hand-coded rules.  
- Exact-quote offsets ensure UI highlights remain precise; pairs that don’t round-trip can be dropped/flagged.

## X API integration (Community Feed / Top Tweets)

To enable the Community Feed widget on each Topic page (shows recent top tweets on the topic), set one of these environment variables before starting the backend. You can place them in a `.env` at the project root (preferred) or in `backend/.env`:

- `X_BEARER_TOKEN` (preferred)
- `TWITTER_BEARER_TOKEN` (fallback)

The token must have access to the Recent Search endpoint. The backend uses the Recent Search API with relevancy sorting and filters out retweets/replies for concise results.

Caching and rate limiting (in-memory):
- `TWEETS_CACHE_TTL` (seconds, default 90) — cache TTL per topic query
- `TWEETS_RATE_WINDOW` (seconds, default 60) — rate-limit window
- `TWEETS_RATE_MAX` (integer, default 20) — max requests per window (global)
- Timeouts and fallbacks:

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
- UI logic on small result sets:
  - If there are 0 top tweets: no summary is shown.
  - If there are 1–3 top tweets: at most 1 summary bullet is displayed.
  - Otherwise: up to 3 bullets are displayed.
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

## Highlight → "Search on X" (Related Tweets)

When you select text in a Topic page's main article content, a small toolbar appears near the selection with two options:

- **Search on X** (with X icon) — updates the left rail's Community Feed from "Top Tweets" to "Related X Tweets to Highlight" and shows tweets related to your selection.
  - In this mode, keywords from your selection are subtly highlighted within each tweet to guide your attention without hurting readability.
- **Suggest Edit** (with pencil icon) — opens the existing edit suggestion modal prefilled with the highlighted text.

How it works:
- Frontend sends the highlighted text to `GET /api/tweets/search?q=...`.
- Backend uses Grok to optimize the query (if `GROK_API` is configured) by suggesting a high-recall OR-based search string (e.g., `(Grok OR API OR xAI)`) and a shortlist of keywords/topics. The prompt explicitly requests OR logic to maximize results.
- If Grok is unavailable, it falls back to extracting keywords and building an OR query from the top 6 most significant terms.
- Search prefers Full-Archive (`/2/tweets/search/all`) and only falls back to Recent if required; a wider candidate pool is used for better recall.
- Results are re-ranked locally with strong keyword/topic emphasis (details below). The UI hides rank badges and the "Trending" pill in this mode.
- Summary bullets and the refresh control are hidden in this mode to keep the panel focused.
- Click the ← button in the feed header to return to regular "Top Tweets".

What is displayed in the UI:
- "Searching for" chips that show a subset of the optimized keywords (up to 8), plus optional topics if provided by Grok.
- Keyword highlighting inside each tweet (subtle background) to make relevant terms easy to spot while keeping readability.
- Editable keywords: users can remove keywords by clicking the × on each chip, or add new keywords via the "+ Add" button.
- Refresh with edits: after editing keywords, click the "↻ Refresh" button in the Search Keywords header to re-search with the updated terms. The frontend builds an OR-based query from the edited keywords (e.g., `(software OR developer OR xai)`) and sends it directly to the backend with `optimize=false` to bypass Grok re-optimization. This ensures the exact edited keywords are used for the search.

API response shape for `GET /api/tweets/search`:
- `{ tweets: TweetItem[], hints?: { query: string, keywords: string[], topics: string[] } }`

Requirements:
- Same X API bearer token as the Top Tweets feature (`X_BEARER_TOKEN` or `TWITTER_BEARER_TOKEN`).
- The search endpoint uses the same caching and single-flight behavior with a short TTL (`TWEETS_CACHE_TTL`).

### Related Tweets: Query + Ranking Details

- Grok query optimization:
  - Highlighted text is sent to Grok to extract critical keywords (entities, names, technical terms) and supporting keywords (synonyms, abbreviations).
  - Grok returns an OR-based query optimized for high recall, plus separate keyword/topic arrays.
  - The page topic (e.g., "elon musk") is automatically added as the first keyword for context.
  - Topics are display-only in the UI; only keywords are used for the actual API query.
  - Fallback (if Grok unavailable): extracts top 6 most significant terms and builds an OR query.

- Retrieval query (backend):
  - OR query using keywords only (quoted for multi-word terms): `(term1 OR "multi word" OR term3) -is:retweet -is:reply lang:en`.
  - Sanitizes invalid characters for X (e.g., `/`) and collapses whitespace.
  - Fetches ~3× requested results to allow Grok-based re-ranking.

- Grok-based ranking (backend):
  - After retrieval, Grok is used to rank tweets by semantic relevance to the highlighted text and keywords.
  - Ranking criteria (in order of importance):
    1. **Semantic match**: Does the tweet discuss the same topic/concept as the highlighted text?
    2. **Keyword coverage**: Does the tweet mention search keywords or related terms?
    3. **Information value**: Does the tweet provide useful insights, news, or discussion?
    4. **Quality signals**: Verified authors and engagement metrics (as tiebreakers only).
  - This approach prioritizes semantic relevance over keyword density, so a tweet discussing the same concept without exact keyword matches ranks higher than an off-topic tweet with keywords.
  - Fallback (if Grok unavailable): returns tweets in X API's relevancy order.

- Fresh-only Refresh:
  - Refresh bypasses cache (`nocache=1`) so a new upstream search is performed; no stale results are served.
  - UI keeps current results visible, showing a subtle shimmer and dot animation while fetching.
