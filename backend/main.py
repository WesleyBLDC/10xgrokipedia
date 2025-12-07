import json
import os
import time
import asyncio
from collections import deque
from typing import Optional
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

# Load .env from the same directory as this file
load_dotenv(Path(__file__).parent / ".env")

app = FastAPI(title="10xGrokipedia API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent

# Load env files (root .env first, then backend/.env to allow local overrides)
load_dotenv(ROOT_DIR / ".env")
load_dotenv(CURRENT_DIR / ".env")

DATA_FILE = CURRENT_DIR / "all_articles_short.json"

# Community Feed config with env overrides
CACHE_TTL_SECONDS = int(os.getenv("TWEETS_CACHE_TTL", "90"))  # default 90s
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("TWEETS_RATE_WINDOW", "60"))  # default 60s
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("TWEETS_RATE_MAX", "20"))  # default 20 reqs/min

# In-memory cache and simple global rate limiter
_tweets_cache: dict[str, tuple[float, list["TweetItem"]]] = {}
_cache_lock = asyncio.Lock()
_rate_lock = asyncio.Lock()
_rate_calls: deque[float] = deque()
SUGGESTIONS_FILE = Path(__file__).parent / "suggestions.json"
GROK_API_KEY = os.getenv("GROK_API_KEY")

if not GROK_API_KEY:
    print("WARNING: GROK_API_KEY not found in .env file!")
else:
    print(f"GROK_API_KEY loaded: {GROK_API_KEY[:15]}...")


# --- Models ---

class Article(BaseModel):
    url: str
    title: str
    content: str
    citations: list[str] = []
    extracted_at: str | None = None
    versions: list[dict] = []

    model_config = {"extra": "ignore"}


class TopicSummary(BaseModel):
    topic: str
    title: str


class TopicDetail(BaseModel):
    topic: str
    title: str
    content: str
    suggestion_count: int = 0


class EditSuggestionInput(BaseModel):
    highlighted_text: str
    summary: str
    sources: list[str] = []


class ReviewResult(BaseModel):
    approved: bool
    reasoning: str
    suggested_content: str | None = None


class SuggestionResponse(BaseModel):
    id: str
    highlighted_text: str
    summary: str
    sources: list[str]
    status: str
    review_result: ReviewResult | None = None
    created_at: str


# --- Helpers ---

def extract_slug(url: str) -> str:
    """Extract topic slug from Grokipedia URL."""
    return url.split("/page/")[-1] if "/page/" in url else url


def load_data() -> list[Article]:
    with open(DATA_FILE) as f:
        return [Article(**item) for item in json.load(f)]


def load_suggestions() -> dict:
    if not SUGGESTIONS_FILE.exists():
        return {}
    with open(SUGGESTIONS_FILE) as f:
        return json.load(f)


def save_suggestions(data: dict):
    with open(SUGGESTIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_suggestion_count(topic_slug: str) -> int:
    suggestions = load_suggestions()
    topic_suggestions = suggestions.get(topic_slug, [])
    return len([s for s in topic_suggestions if s["status"] == "pending"])


def normalize_quotes(text: str) -> str:
    """Normalize smart quotes to regular quotes for matching."""
    replacements = {
        '\u2018': "'",  # '
        '\u2019': "'",  # '
        '\u201C': '"',  # "
        '\u201D': '"',  # "
        '\u2013': '-',  # –
        '\u2014': '-',  # —
    }
    for smart, regular in replacements.items():
        text = text.replace(smart, regular)
    return text


def strip_markdown_links(text: str) -> str:
    """Convert [text](url) markdown links to just text for matching."""
    # Replace [text](url) with just text, and [](url) with nothing
    result = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', text)
    return result


def find_and_replace_fuzzy(content: str, highlighted: str, replacement: str) -> str | None:
    """Find highlighted text in content accounting for markdown and smart quotes."""
    # Normalize both for comparison
    norm_highlighted = normalize_quotes(highlighted)
    norm_content = normalize_quotes(content)

    # Also strip markdown links for comparison
    stripped_content = strip_markdown_links(norm_content)
    stripped_highlighted = strip_markdown_links(norm_highlighted)

    # Try to find in stripped content
    stripped_idx = stripped_content.find(stripped_highlighted)
    if stripped_idx == -1:
        return None

    # Build a mapping from stripped positions to original positions
    # For each character in stripped content, track where it came from in original
    stripped_to_original = []
    orig_i = 0

    while orig_i < len(norm_content):
        if norm_content[orig_i] == '[':
            # Check if this is a markdown link
            bracket_end = norm_content.find(']', orig_i)
            if bracket_end != -1:
                paren_start = bracket_end + 1
                if paren_start < len(norm_content) and norm_content[paren_start] == '(':
                    paren_end = norm_content.find(')', paren_start)
                    if paren_end != -1:
                        # This is a markdown link [text](url) or [](url)
                        # The link text maps to stripped content
                        link_text = norm_content[orig_i+1:bracket_end]
                        if len(link_text) > 0:
                            for j in range(len(link_text)):
                                stripped_to_original.append(orig_i + 1 + j)
                        # Skip entire link syntax (empty links [](url) are completely removed)
                        orig_i = paren_end + 1
                        continue

        # Regular character
        stripped_to_original.append(orig_i)
        orig_i += 1

    # Now map the found position back to original
    if stripped_idx >= len(stripped_to_original):
        return None

    original_start = stripped_to_original[stripped_idx]

    # For the end position, we need to find where the highlighted text ends
    end_stripped_idx = stripped_idx + len(stripped_highlighted) - 1
    if end_stripped_idx >= len(stripped_to_original):
        end_stripped_idx = len(stripped_to_original) - 1

    original_end = stripped_to_original[end_stripped_idx] + 1

    # Extend to include any trailing markdown link that we might be in the middle of
    # Check if we're ending inside a markdown link's text
    remaining = norm_content[original_end:]
    if remaining:
        # Look for pattern ](url) which would indicate we're in a link
        match = re.match(r'^[^\[\]]*\]\([^)]*\)', remaining)
        if match:
            original_end += match.end()

    # Replace in original content using the mapped positions
    return content[:original_start] + replacement + content[original_end:]


# --- Static Topic Endpoints (must come first) ---

@app.get("/api/topics")
def get_topics() -> list[TopicSummary]:
    """Get all topics (for search)."""
    data = load_data()
    return [
        TopicSummary(topic=extract_slug(a.url), title=a.title)
        for a in data
    ]


@app.get("/api/topics/search")
def search_topics(q: str = "") -> list[TopicSummary]:
    """Search topics by query string."""
    data = load_data()
    query = q.lower()
    results = [
        TopicSummary(topic=extract_slug(a.url), title=a.title)
        for a in data
        if query in a.title.lower() or query in extract_slug(a.url).lower()
    ]
    return results


# --- Suggestion Endpoints (must come BEFORE catch-all topic route) ---
# IMPORTANT: Specific routes with /review/, /apply/, /reject/ must come BEFORE
# the generic POST route because {topic_slug:path} is greedy and captures everything.

@app.get("/api/suggestions/{topic_slug:path}")
def get_suggestions(topic_slug: str) -> list[SuggestionResponse]:
    """Get all suggestions for a topic."""
    decoded_slug = unquote(topic_slug)
    suggestions = load_suggestions()
    topic_suggestions = suggestions.get(decoded_slug, [])
    return [SuggestionResponse(**s) for s in topic_suggestions]


@app.post("/api/suggestions/{topic_slug:path}/review/{suggestion_id}")
async def review_suggestion(topic_slug: str, suggestion_id: str) -> ReviewResult:
    """Review a suggestion using Grok API."""
    decoded_slug = unquote(topic_slug)
    suggestions = load_suggestions()

    if decoded_slug not in suggestions:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Find the suggestion
    suggestion = None
    for s in suggestions[decoded_slug]:
        if s["id"] == suggestion_id:
            suggestion = s
            break

    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Get article content
    data = load_data()
    article_content = None
    for a in data:
        if extract_slug(a.url) == decoded_slug:
            article_content = a.content
            break

    if not article_content:
        raise HTTPException(status_code=404, detail="Article not found")

    # Call Grok API
    sources_text = "\n".join(suggestion["sources"]) if suggestion["sources"] else "No sources provided"

    prompt = f"""You are reviewing a suggested edit for an encyclopedia article.

CURRENT ARTICLE CONTENT:
{article_content[:3000]}

HIGHLIGHTED TEXT TO EDIT:
{suggestion["highlighted_text"]}

USER'S SUGGESTED CHANGE:
{suggestion["summary"]}

SUPPORTING SOURCES:
{sources_text}

Evaluate if this suggestion improves the article's accuracy. Consider:
1. Is the suggested change factually accurate?
2. Do the sources support the change?
3. Does it improve the article?

Respond in JSON format:
{{
    "approved": true/false,
    "reasoning": "Brief explanation of your decision",
    "suggested_content": "If approved, provide the corrected text to replace the highlighted section. If rejected, set to null."
}}"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GROK_API_KEY}"
                },
                json={
                    "messages": [
                        {"role": "system", "content": "You are a fact-checking assistant for an encyclopedia. Always respond with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "model": "grok-3-latest",
                    "stream": False,
                    "temperature": 0
                },
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()

            # Parse the response
            content = result["choices"][0]["message"]["content"]
            # Try to extract JSON from the response
            try:
                review_data = json.loads(content)
            except json.JSONDecodeError:
                # Try to find JSON in the response
                json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                if json_match:
                    review_data = json.loads(json_match.group())
                else:
                    review_data = {
                        "approved": False,
                        "reasoning": "Failed to parse AI response",
                        "suggested_content": None
                    }

            review_result = ReviewResult(
                approved=review_data.get("approved", False),
                reasoning=review_data.get("reasoning", ""),
                suggested_content=review_data.get("suggested_content")
            )

            # Update suggestion status
            suggestion["status"] = "reviewed"
            suggestion["review_result"] = {
                "approved": review_result.approved,
                "reasoning": review_result.reasoning,
                "suggested_content": review_result.suggested_content
            }
            save_suggestions(suggestions)

            return review_result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grok API error: {str(e)}")


@app.post("/api/suggestions/{topic_slug:path}/apply/{suggestion_id}")
def apply_suggestion(topic_slug: str, suggestion_id: str):
    """Apply an approved suggestion to the article."""
    decoded_slug = unquote(topic_slug)
    suggestions = load_suggestions()

    if decoded_slug not in suggestions:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Find the suggestion
    suggestion = None
    for s in suggestions[decoded_slug]:
        if s["id"] == suggestion_id:
            suggestion = s
            break

    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if suggestion["status"] != "reviewed":
        raise HTTPException(status_code=400, detail="Suggestion must be reviewed first")

    if not suggestion["review_result"] or not suggestion["review_result"].get("approved"):
        raise HTTPException(status_code=400, detail="Suggestion was not approved")

    # Load and update article
    with open(DATA_FILE) as f:
        articles = json.load(f)

    for article in articles:
        if extract_slug(article["url"]) == decoded_slug:
            # Save version history
            if "versions" not in article:
                article["versions"] = []
            article["versions"].append({
                "content": article["content"],
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })

            # Apply the change
            suggested_content = suggestion["review_result"]["suggested_content"]
            if suggested_content:
                highlighted = suggestion["highlighted_text"]
                # Try exact match first
                if highlighted in article["content"]:
                    article["content"] = article["content"].replace(highlighted, suggested_content)
                else:
                    # Try fuzzy matching (handles smart quotes and markdown links)
                    new_content = find_and_replace_fuzzy(article["content"], highlighted, suggested_content)
                    if new_content:
                        article["content"] = new_content
            break

    # Save updated articles
    with open(DATA_FILE, "w") as f:
        json.dump(articles, f, indent=2)

    # Mark suggestion as applied
    suggestion["status"] = "applied"
    save_suggestions(suggestions)

    return {"message": "Suggestion applied successfully"}


@app.post("/api/suggestions/{topic_slug:path}/reject/{suggestion_id}")
def reject_suggestion(topic_slug: str, suggestion_id: str):
    """Reject a suggestion."""
    decoded_slug = unquote(topic_slug)
    suggestions = load_suggestions()

    if decoded_slug not in suggestions:
        raise HTTPException(status_code=404, detail="Topic not found")

    for s in suggestions[decoded_slug]:
        if s["id"] == suggestion_id:
            s["status"] = "rejected"
            save_suggestions(suggestions)
            return {"message": "Suggestion rejected"}

    raise HTTPException(status_code=404, detail="Suggestion not found")


# Generic submit route MUST come AFTER specific routes due to greedy :path
@app.post("/api/suggestions/{topic_slug:path}")
def submit_suggestion(topic_slug: str, suggestion: EditSuggestionInput) -> SuggestionResponse:
    """Submit a new edit suggestion for a topic."""
    decoded_slug = unquote(topic_slug)
    suggestions = load_suggestions()

    if decoded_slug not in suggestions:
        suggestions[decoded_slug] = []

    new_suggestion = {
        "id": str(uuid.uuid4()),
        "highlighted_text": suggestion.highlighted_text,
        "summary": suggestion.summary,
        "sources": suggestion.sources,
        "status": "pending",
        "review_result": None,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }

    suggestions[decoded_slug].append(new_suggestion)
    save_suggestions(suggestions)

    return SuggestionResponse(**new_suggestion)


# --- Version History Endpoint ---

class VersionSummary(BaseModel):
    index: int
    timestamp: str


class VersionDetail(BaseModel):
    index: int
    timestamp: str
    content: str


@app.get("/api/topics/{topic_slug:path}/versions")
def get_versions(topic_slug: str) -> list[VersionSummary]:
    """Get version history for a topic."""
    decoded_slug = unquote(topic_slug)
    data = load_data()

    for a in data:
        if extract_slug(a.url) == decoded_slug:
            versions = []
            for i, v in enumerate(a.versions):
                versions.append(VersionSummary(index=i, timestamp=v["timestamp"]))
            return versions

    raise HTTPException(status_code=404, detail="Topic not found")


@app.get("/api/topics/{topic_slug:path}/versions/{version_index}")
def get_version(topic_slug: str, version_index: int) -> VersionDetail:
    """Get a specific version of a topic."""
    decoded_slug = unquote(topic_slug)
    data = load_data()

    for a in data:
        if extract_slug(a.url) == decoded_slug:
            if version_index < 0 or version_index >= len(a.versions):
                raise HTTPException(status_code=404, detail="Version not found")
            v = a.versions[version_index]
            return VersionDetail(index=version_index, timestamp=v["timestamp"], content=v["content"])

    raise HTTPException(status_code=404, detail="Topic not found")


# --- Dynamic Topic Endpoint (catch-all, must come LAST) ---

@app.get("/api/topics/{topic_slug:path}")
def get_topic(topic_slug: str) -> TopicDetail:
    """Get a specific topic by slug."""
    data = load_data()
    decoded_slug = unquote(topic_slug)

    for a in data:
        if extract_slug(a.url) == decoded_slug:
            return TopicDetail(
                topic=extract_slug(a.url),
                title=a.title,
                content=a.content,
                suggestion_count=get_suggestion_count(decoded_slug)
            )
    raise HTTPException(status_code=404, detail="Topic not found")


# ---- Community Feed (X/Twitter) ----
class TweetItem(BaseModel):
    id: str
    text: str
    author_username: str
    author_name: Optional[str] = None
    author_profile_image_url: Optional[str] = None
    created_at: Optional[str] = None
    like_count: Optional[int] = None
    retweet_count: Optional[int] = None
    reply_count: Optional[int] = None
    quote_count: Optional[int] = None
    url: str
    score: Optional[float] = None


def _get_x_bearer_token() -> Optional[str]:
    # Support either env var name
    return os.getenv("X_BEARER_TOKEN") or os.getenv("TWITTER_BEARER_TOKEN")


def _compute_score(tweet: dict, user: dict) -> float:
    metrics = tweet.get("public_metrics", {}) or {}
    likes = float(metrics.get("like_count", 0) or 0)
    rts = float(metrics.get("retweet_count", 0) or 0)
    replies = float(metrics.get("reply_count", 0) or 0)
    quotes = float(metrics.get("quote_count", 0) or 0)
    # Author followers for normalization
    um = (user or {}).get("public_metrics", {}) or {}
    followers = float(um.get("followers_count", 0) or 0)
    # Engagement score emphasizing RTs and quotes, then normalize by audience size
    raw = likes + 2.0 * rts + 1.5 * quotes + 0.5 * replies
    norm = (max(50.0, followers) ** 0.7)  # dampen large accounts
    return raw / norm if norm > 0 else raw


async def _fetch_recent_top_tweets(query: str, return_count: int = 10, pool_size: int = 50) -> list[TweetItem]:
    # Fetch and rank candidates from both recent and full-archive search, then return the top N by score.
    token = _get_x_bearer_token()
    if not token:
        raise HTTPException(status_code=501, detail="X API bearer token not configured. Set X_BEARER_TOKEN or TWITTER_BEARER_TOKEN.")

    recent_url = "https://api.x.com/2/tweets/search/recent"
    all_url = "https://api.x.com/2/tweets/search/all"

    # Attempt to bias toward relevance server-side, we'll re-rank by engagement score
    params = {
        "query": f"{query} -is:retweet -is:reply lang:en",
        "max_results": str(max(10, min(pool_size, 100))),
        "sort_order": "relevancy",
        "tweet.fields": "public_metrics,created_at,lang,author_id",
        "expansions": "author_id",
        "user.fields": "username,name,profile_image_url,public_metrics",
    }

    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Fetch RECENT search
        try:
            resp = await client.get(recent_url, params=params, headers=headers)
            if resp.status_code == 404:
                # Some proxies may not resolve api.x.com; try twitter domain
                alt_url = "https://api.twitter.com/2/tweets/search/recent"
                resp = await client.get(alt_url, params=params, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Forward error details to client
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to reach X API: {e}")

        data_recent = resp.json()
        tweets_recent = data_recent.get("data", []) or []
        includes_recent = data_recent.get("includes", {}) or {}
        users_recent = {u.get("id"): u for u in includes_recent.get("users", [])}

        # Fetch FULL-ARCHIVE search as well; ignore entitlement/network errors gracefully
        try:
            resp2 = await client.get(all_url, params=params, headers=headers)
            if resp2.status_code == 404:
                alt_url_all = "https://api.twitter.com/2/tweets/search/all"
                resp2 = await client.get(alt_url_all, params=params, headers=headers)
            # If forbidden/not entitled, do not hard-fail: return empty list gracefully
            if resp2.status_code in (401, 403):
                data_all = {"data": [], "includes": {"users": []}}
            else:
                resp2.raise_for_status()
                data_all = resp2.json()
        except httpx.HTTPStatusError as e:
            # If the fallback API is not available to this token, degrade gracefully
            if e.response is not None and e.response.status_code in (401, 403, 404):
                data_all = {"data": [], "includes": {"users": []}}
            else:
                raise HTTPException(status_code=e.response.status_code if e.response else 502, detail=(e.response.text if e.response else str(e)))
        except httpx.RequestError:
            # Network issues on fallback: degrade gracefully with empty list
            data_all = {"data": [], "includes": {"users": []}}

        tweets_all = data_all.get("data", []) or []
        includes_all = data_all.get("includes", {}) or {}
        users_all = {u.get("id"): u for u in includes_all.get("users", [])}

        # Combine candidates and user maps; prefer 'recent' user entries then 'all'
        combined_users = {**users_all, **users_recent}
        combined_map = {}
        for t in tweets_all:
            tid = t.get("id")
            if tid:
                combined_map[tid] = (t, users_all.get(t.get("author_id")))
        for t in tweets_recent:
            tid = t.get("id")
            if tid:
                combined_map[tid] = (t, users_recent.get(t.get("author_id")))

        # Rank combined
        ranked: list[tuple[float, dict, dict]] = []
        for tid, (t, u) in combined_map.items():
            score = _compute_score(t, u or {})
            ranked.append((score, t, u or {}))

        if not ranked:
            return []

        ranked.sort(key=lambda x: x[0], reverse=True)
        ranked = ranked[:max(1, return_count * 3)]  # keep more buffer when combining
        out: list[TweetItem] = []
        for score, t, u in ranked[:return_count]:
            tid = t.get("id")
            text = t.get("text", "")
            created_at = t.get("created_at")
            metrics = t.get("public_metrics", {}) or {}
            username = (u or {}).get("username")
            name = (u or {}).get("name")
            pfp = (u or {}).get("profile_image_url")
            url = f"https://x.com/{username}/status/{tid}" if username and tid else f"https://x.com/i/web/status/{tid}"
            out.append(
                TweetItem(
                    id=tid,
                    text=text,
                    author_username=username or "",
                    author_name=name,
                    author_profile_image_url=pfp,
                    created_at=created_at,
                    like_count=metrics.get("like_count"),
                    retweet_count=metrics.get("retweet_count"),
                    reply_count=metrics.get("reply_count"),
                    quote_count=metrics.get("quote_count"),
                    url=url,
                    score=score,
                )
            )
        return out


@app.get("/api/topics/{topic_slug}/tweets")
async def get_topic_tweets(topic_slug: str, max_results: int = 10) -> list[TweetItem]:
    """Recent top tweets for a topic. Uses X API recent search with relevancy sort.

    - Requires env var `X_BEARER_TOKEN` (or `TWITTER_BEARER_TOKEN`).
    - `topic_slug` is the Grokipedia slug; converted to a phrase query.
    """
    # Decode URL-encoded slugs (e.g., %20 -> space)
    decoded_slug = unquote(topic_slug)
    # Convert slug-like to a phrase: underscores and hyphens to spaces, wrap in quotes
    phrase = decoded_slug.replace("_", " ").replace("-", " ").strip()
    if not phrase:
        raise HTTPException(status_code=400, detail="Empty topic slug")
    query = f'"{phrase}"'

    # Build cache key based on normalized query and max_results
    key = f"q={query}|n={max_results}"

    # Attempt to read from cache
    now = time.time()
    async with _cache_lock:
        if key in _tweets_cache:
            ts, items = _tweets_cache[key]
            if now - ts < CACHE_TTL_SECONDS:
                return items
            else:
                # expired; drop entry
                _tweets_cache.pop(key, None)

    # Rate limiting: simple global window limiter
    async with _rate_lock:
        # remove old entries
        while _rate_calls and (now - _rate_calls[0] > RATE_LIMIT_WINDOW_SECONDS):
            _rate_calls.popleft()
        if len(_rate_calls) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="Rate limit exceeded for tweets endpoint. Please try again later.")
        _rate_calls.append(now)

    # Fetch fresh results
    items = await _fetch_recent_top_tweets(query=query, return_count=max_results)

    # Store in cache
    async with _cache_lock:
        _tweets_cache[key] = (time.time(), items)

    return items


@app.post("/api/topics/{topic_slug}/tweets/refresh", status_code=204)
async def refresh_topic_tweets(topic_slug: str) -> Response:
    decoded_slug = unquote(topic_slug)
    phrase = decoded_slug.replace("_", " ").replace("-", " ").strip()
    if not phrase:
        raise HTTPException(status_code=400, detail="Empty topic slug")
    query = f'"{phrase}"'
    key_prefix = f"q={query}|"
    async with _cache_lock:
        to_delete = [k for k in list(_tweets_cache.keys()) if k.startswith(key_prefix)]
        for k in to_delete:
            _tweets_cache.pop(k, None)
    return Response(status_code=204)
