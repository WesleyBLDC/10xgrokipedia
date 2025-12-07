import asyncio
import json
import os
import re
import time
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

import html2text
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from urllib.parse import urlparse

# Load .env from the same directory as this file
load_dotenv(Path(__file__).parent / ".env")

app = FastAPI(title="10xGrokipedia API")

# CORS: allow all origins for local/dev use (frontend talks to http://localhost:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
DATA_FILE = Path(__file__).parent / "all_articles_short.json"
CITATION_EVALUATIONS_FILE = Path(__file__).parent / "citation_bias_evaluations.json"

# Load env files (root .env first, then backend/.env to allow local overrides)
load_dotenv(ROOT_DIR / ".env")
load_dotenv(CURRENT_DIR / ".env")

DATA_FILE = CURRENT_DIR / "all_articles_short.json"

# Community Feed config with env overrides
CACHE_TTL_SECONDS = int(os.getenv("TWEETS_CACHE_TTL", "90"))  # default 90s
SUMMARY_TTL_SECONDS = int(os.getenv("TWEETS_SUMMARY_TTL", "600"))  # default 10m
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("TWEETS_RATE_WINDOW", "60"))  # default 60s
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("TWEETS_RATE_MAX", "20"))  # default 20 reqs/min
TRENDING_HOURS = int(os.getenv("TWEETS_TRENDING_HOURS", "168"))  # default 7d (168h)
TRENDING_TOP_K = int(os.getenv("TWEETS_TRENDING_TOP_K", "3"))  # default top 3
# Preview flags (optional): force trending for top-N or specific ranks (1-based)
TRENDING_PREVIEW_TOP_K = int(os.getenv("TWEETS_TRENDING_PREVIEW_TOP_K", "0"))
_TPR = os.getenv("TWEETS_TRENDING_PREVIEW_RANKS", "").strip()
TRENDING_PREVIEW_RANKS = {int(x) for x in _TPR.split(',') if x.strip().isdigit()} if _TPR else set()
VERIFIED_BOOST = float(os.getenv("TWEETS_VERIFIED_BOOST", "1.1"))  # 10% lift by default



# In-memory cache and simple global rate limiter
_tweets_cache: dict[str, tuple[float, list["TweetItem"]]] = {}
_summary_cache: dict[str, tuple[float, List[str]]] = {}
_cache_lock = asyncio.Lock()
_rate_lock = asyncio.Lock()
_rate_calls: deque[float] = deque()
SUGGESTIONS_FILE = Path(__file__).parent / "suggestions.json"
GROK_API_KEY = os.getenv("GROK_API_KEY")
_inflight_tasks: dict[str, asyncio.Task] = {}

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

class AggregateBiasResponse(BaseModel):
    article_title: str
    article_url: str
    citation_count: int
    evaluated_citation_count: int
    average_factual_score: float
    factual_label: str
    average_bias_score: float
    bias_label: str


class CitationBiasResponse(BaseModel):
    citation_url: str
    factual_score: float
    factual_label: str
    bias_score: float
    bias_label: str


class SearchHints(BaseModel):
    query: str
    keywords: List[str] = []
    topics: List[str] = []


class SearchResponse(BaseModel):
    tweets: List["TweetItem"]
    hints: SearchHints | None = None


def extract_slug(url: str) -> str:
    """Extract topic slug from Grokipedia URL."""
    return url.split("/page/")[-1] if "/page/" in url else url


def load_data() -> list[dict]:
    """Load articles as dictionaries to preserve all fields including citations."""
    with open(DATA_FILE) as f:
        return json.load(f)


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
        TopicSummary(topic=extract_slug(a['url']), title=a['title'])
        for a in data
    ]


@app.get("/api/topics/search")
def search_topics(q: str = "") -> list[TopicSummary]:
    """Search topics by query string."""
    data = load_data()
    query = q.lower()
    results = [
        TopicSummary(topic=extract_slug(a['url']), title=a['title'])
        for a in data
        if query in a['title'].lower() or query in extract_slug(a['url']).lower()
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
        if extract_slug(a["url"]) == decoded_slug:
            versions = []
            for i, v in enumerate(a.get("versions", [])):
                versions.append(VersionSummary(index=i, timestamp=v["timestamp"]))
            return versions

    raise HTTPException(status_code=404, detail="Topic not found")


@app.get("/api/topics/{topic_slug:path}/versions/{version_index}")
def get_version(topic_slug: str, version_index: int) -> VersionDetail:
    """Get a specific version of a topic."""
    decoded_slug = unquote(topic_slug)
    data = load_data()

    for a in data:
        if extract_slug(a['url']) == decoded_slug:
            versions = a.get('versions', [])
            if version_index < 0 or version_index >= len(versions):
                raise HTTPException(status_code=404, detail="Version not found")
            v = versions[version_index]
            return VersionDetail(index=version_index, timestamp=v["timestamp"], content=v["content"])

    raise HTTPException(status_code=404, detail="Topic not found")


# ---- Community Feed Models (X/Twitter) ----

class TweetItem(BaseModel):
    id: str
    text: str
    author_username: str
    author_name: Optional[str] = None
    author_profile_image_url: Optional[str] = None
    author_verified: Optional[bool] = None
    author_verified_type: Optional[str] = None
    created_at: Optional[str] = None
    like_count: Optional[int] = None
    retweet_count: Optional[int] = None
    reply_count: Optional[int] = None
    quote_count: Optional[int] = None
    url: str
    score: Optional[float] = None
    trending: Optional[bool] = None


class TweetsSummary(BaseModel):
    bullets: List[str]
    model: Optional[str] = None
    cached: bool = False


# --- Tweets Endpoints (must come BEFORE catch-all topic route) ---

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
                _tweets_cache.pop(key, None)

        # Single-flight: if another request is already fetching, await it
        if key in _inflight_tasks:
            task = _inflight_tasks[key]
            joiner = True
        else:
            # Rate limiting only for the creator of the task
            async with _rate_lock:
                while _rate_calls and (now - _rate_calls[0] > RATE_LIMIT_WINDOW_SECONDS):
                    _rate_calls.popleft()
                if len(_rate_calls) >= RATE_LIMIT_MAX_REQUESTS:
                    # serve stale if available (even if expired)
                    if key in _tweets_cache:
                        return _tweets_cache[key][1]
                    raise HTTPException(status_code=429, detail="Rate limit exceeded for tweets endpoint. Please try again later.")
                _rate_calls.append(now)
            task = asyncio.create_task(_fetch_recent_top_tweets(query=query, return_count=max_results))
            _inflight_tasks[key] = task
            joiner = False

    # Await the task outside the lock
    try:
        items = await task
    except HTTPException as e:
        # On upstream 429 or errors, try to serve stale if available
        async with _cache_lock:
            if key in _tweets_cache:
                return _tweets_cache[key][1]
        raise e
    finally:
        if not joiner:
            async with _cache_lock:
                _inflight_tasks.pop(key, None)

    # Store in cache (creator only)
    if not joiner:
        async with _cache_lock:
            _tweets_cache[key] = (time.time(), items)

    return items


async def _suggest_search_query(highlight_text: str) -> SearchHints | None:
    token = _get_grok_api()
    if not token:
        return None
    base = _get_grok_base().rstrip("/")
    model = _get_grok_model()
    url = f"{base}/chat/completions"

    system_prompt = (
        "You are an expert at crafting HIGH-RECALL queries for X (Twitter) search. "
        "Given a user-selected passage, extract keywords in two tiers:\n"
        "1. CRITICAL: Core entities, names, technical terms (most distinctive)\n"
        "2. SUPPORTING: Related concepts, synonyms, abbreviations for broader recall\n\n"
        "CRITICAL RULES:\n"
        "- Query MUST use OR logic: (term1 OR term2 OR term3)\n"
        "- Include synonyms and abbreviations (e.g., 'AI' alongside 'artificial intelligence')\n"
        "- Prioritize named entities, product names, and technical jargon\n"
        "- Avoid generic words like 'new', 'latest', 'best', 'important'\n"
        "- Include 5-10 key terms connected with OR. Keep query under 128 characters."
    )

    user_prompt = (
        "Selected passage:\n" + highlight_text.strip()[:500] + "\n\n"
        "Return ONLY compact JSON with keys:\n"
        "- query: string using OR logic like '(Grok OR API OR xAI OR chatbot)' - MUST use OR between ALL terms\n"
        "- keywords: array of 6-12 individual search terms ordered by importance (critical first, supporting last)\n"
        "- topics: array of 2-4 broader topic labels (e.g., 'artificial intelligence', 'tech industry')"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 256,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                import json as _json
                obj = _json.loads(content[start:end+1])
                q = str(obj.get("query", "")).strip()
                kws = [str(x).strip() for x in (obj.get("keywords") or []) if str(x).strip()]
                tps = [str(x).strip() for x in (obj.get("topics") or []) if str(x).strip()]
                if q:
                    return SearchHints(query=q, keywords=kws[:12], topics=tps[:5])
            return None
    except Exception:
        return None


async def _grok_rank_tweets(
    tweets: List[TweetItem],
    highlighted_text: str,
    keywords: List[str],
    max_results: int = 10
) -> List[TweetItem]:
    """Use Grok to rank tweets by relevance to highlighted text and keywords."""
    if not tweets:
        return []

    token = _get_grok_api()
    if not token:
        # Fallback: return tweets as-is (already sorted by X API relevancy)
        return tweets[:max_results]

    base = _get_grok_base().rstrip("/")
    model = _get_grok_model()
    url = f"{base}/chat/completions"

    # Prepare tweet data for Grok (limit to avoid token overflow)
    tweet_summaries = []
    for i, t in enumerate(tweets[:20]):  # Max 20 candidates
        # Include key metrics for context
        metrics = f"❤{t.like_count or 0} ↻{t.retweet_count or 0}"
        verified = " [verified]" if t.author_verified else ""
        tweet_summaries.append(
            f"{i+1}. @{t.author_username}{verified}: {t.text[:200]}... ({metrics})"
        )

    tweets_block = "\n".join(tweet_summaries)
    keywords_str = ", ".join(keywords[:10]) if keywords else "N/A"

    system_prompt = (
        "You are an expert at ranking tweets by relevance. Given a user's highlighted text "
        "and search keywords, rank the tweets from MOST to LEAST relevant.\n\n"
        "Relevance criteria (in order of importance):\n"
        "1. SEMANTIC MATCH: Does the tweet discuss the same topic/concept as the highlighted text?\n"
        "2. KEYWORD COVERAGE: Does the tweet mention the search keywords or related terms?\n"
        "3. INFORMATION VALUE: Does the tweet provide useful insights, news, or discussion?\n"
        "4. QUALITY SIGNALS: Verified authors, engagement metrics (as tiebreakers only)\n\n"
        "IMPORTANT: Prioritize semantic relevance over keyword density. A tweet discussing "
        "the same concept without exact keyword matches is MORE relevant than a tweet "
        "with keywords but off-topic content."
    )

    user_prompt = (
        f"HIGHLIGHTED TEXT:\n{highlighted_text[:400]}\n\n"
        f"SEARCH KEYWORDS: {keywords_str}\n\n"
        f"TWEETS TO RANK:\n{tweets_block}\n\n"
        f"Return ONLY a JSON array of tweet numbers in order of relevance (most relevant first).\n"
        f"Example: [3, 1, 7, 2, 5, 4, 6, 8, 9, 10]\n"
        f"Return the top {max_results} most relevant tweets."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,  # Low temperature for consistent ranking
        "max_tokens": 128,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            # Parse the ranking array from response
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end != -1 and end > start:
                ranking = json.loads(content[start:end + 1])
                if isinstance(ranking, list):
                    # Convert 1-indexed to 0-indexed and filter valid indices
                    reranked = []
                    seen = set()
                    for idx in ranking:
                        if isinstance(idx, int) and 1 <= idx <= len(tweets) and idx not in seen:
                            reranked.append(tweets[idx - 1])
                            seen.add(idx)
                            if len(reranked) >= max_results:
                                break

                    # If Grok returned fewer than requested, append remaining by original order
                    if len(reranked) < max_results:
                        for i, t in enumerate(tweets):
                            if (i + 1) not in seen:
                                reranked.append(t)
                                if len(reranked) >= max_results:
                                    break

                    print(f"[grok_rank] Ranked {len(reranked)} tweets, order: {ranking[:max_results]}")
                    return reranked

            # Parsing failed, return original order
            print("[grok_rank] Failed to parse ranking, using original order")
            return tweets[:max_results]

    except Exception as e:
        print(f"[grok_rank] Error: {e}, using original order")
        return tweets[:max_results]


@app.get("/api/tweets/search")
async def search_tweets(q: str, max_results: int = 10, optimize: bool = True, nocache: bool = False) -> SearchResponse:
    """Search X for tweets related to an arbitrary text query (used for highlight search).

    - Requires env var `X_BEARER_TOKEN` (or `TWITTER_BEARER_TOKEN`).
    - `q` is the raw text highlighted by the user.
    """
    phrase = (q or "").strip()
    if not phrase:
        raise HTTPException(status_code=400, detail="Empty query")
    # Build a keyword-centric OR query to avoid strict phrase matching on long selections
    def _extract_terms(text: str, max_terms: int = 12) -> list[str]:
        text = text.lower()
        tokens = re.findall(r"[\w'-]+", text, flags=re.UNICODE)
        stop = {
            "the","a","an","and","or","but","if","then","else","for","of","in","to","on","at","by","with","as","from","that","this","these","those","is","are","was","were","be","been","being","it","its","into","over","about","after","before","not","no","yes","we","you","they","their","our","his","her","him","she","he","them","which","who","whom","what","when","where","why","how"
        }
        counts: dict[str, int] = {}
        for t in tokens:
            s = t.strip("-'")
            if not s or len(s) < 3 or s in stop:
                continue
            counts[s] = counts.get(s, 0) + 1
        ordered = sorted(counts.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
        return [w for w, _ in ordered[:max_terms]]

    hints: SearchHints | None = None
    if optimize:
        hints = await _suggest_search_query(phrase)
    if hints and hints.query:
        query = hints.query
    else:
        # Check if the input already looks like a pre-built OR query (from frontend rawMode)
        # Pattern: starts with ( and contains OR
        is_prebuilt_query = phrase.startswith("(") and " OR " in phrase.upper()
        if is_prebuilt_query:
            # Use the query as-is - it's already formatted by the frontend
            query = phrase
        else:
            terms = _extract_terms(phrase)
            if not terms:
                parts = [p for p in re.sub(r"\s+", " ", phrase).split(" ") if len(p) >= 3]
                terms = parts[:8]
            # Limit to 6 most important terms to avoid overly complex queries
            terms = terms[:6]
            pieces = [f'"{t}"' if (" " in t) else t for t in terms]
            or_block = " OR ".join(pieces) if pieces else phrase
            query = f"({or_block})"

    # Sanitize query for X API: remove or space out disallowed characters like '/'
    def _sanitize_x_query(s: str) -> str:
        # Replace slashes with spaces (X rejects them), and collapse repeated whitespace.
        s = re.sub(r"/+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    query = _sanitize_x_query(query)

    # Debug: log the final query being used
    print(f"[search_tweets] optimize={optimize}, is_prebuilt={phrase.startswith('(') and ' OR ' in phrase.upper()}, final_query={query}")

    key = f"q={query}|n={max_results}"
    now = time.time()

    # We will fetch a larger candidate pool (3x) to re-rank by keyword coverage + engagement
    fetch_count = max_results * 3

    async with _cache_lock:
        if not nocache:
            if key in _tweets_cache:
                ts, items = _tweets_cache[key]
                if now - ts < CACHE_TTL_SECONDS:
                    return SearchResponse(tweets=items, hints=hints)
                else:
                    _tweets_cache.pop(key, None)

            if key in _inflight_tasks:
                task = _inflight_tasks[key]
                joiner = True
            else:
                async with _rate_lock:
                    while _rate_calls and (now - _rate_calls[0] > RATE_LIMIT_WINDOW_SECONDS):
                        _rate_calls.popleft()
                    if len(_rate_calls) >= RATE_LIMIT_MAX_REQUESTS:
                        if key in _tweets_cache:
                            return SearchResponse(tweets=_tweets_cache[key][1], hints=hints)
                        raise HTTPException(status_code=429, detail="Rate limit exceeded for tweets endpoint. Please try again later.")
                    _rate_calls.append(now)
                task = asyncio.create_task(_fetch_recent_top_tweets(query=query, return_count=fetch_count, pool_size=100))
                _inflight_tasks[key] = task
                joiner = False
        else:
            # nocache: always create a fresh task, don't join inflight
            async with _rate_lock:
                while _rate_calls and (now - _rate_calls[0] > RATE_LIMIT_WINDOW_SECONDS):
                    _rate_calls.popleft()
                if len(_rate_calls) >= RATE_LIMIT_MAX_REQUESTS:
                    raise HTTPException(status_code=429, detail="Rate limit exceeded for tweets endpoint. Please try again later.")
                _rate_calls.append(now)
            task = asyncio.create_task(_fetch_recent_top_tweets(query=query, return_count=fetch_count, pool_size=100))
            joiner = False

    try:
        items = await task
    except HTTPException as e:
        if not nocache:
            async with _cache_lock:
                if key in _tweets_cache:
                    return SearchResponse(tweets=_tweets_cache[key][1], hints=hints)
        raise e
    finally:
        if not joiner:
            async with _cache_lock:
                _inflight_tasks.pop(key, None)

    # Use Grok to rank tweets by semantic relevance to highlighted text
    # Gather keywords from hints or extract from query
    ranking_keywords: list[str] = []
    if hints:
        ranking_keywords = list(hints.keywords or []) + list(hints.topics or [])
    if not ranking_keywords:
        # Fallback: extract terms from query
        def _extract_rank_terms(qs: str) -> list[str]:
            qs = re.sub(r"-is:retweet|-is:reply|lang:[a-zA-Z-]+", " ", qs)
            qs = qs.replace("(", " ").replace(")", " ").replace("\"", " ")
            qs = re.sub(r"\bOR\b", " ", qs, flags=re.IGNORECASE)
            qs = re.sub(r"\s+", " ", qs).strip().lower()
            return [t for t in qs.split(" ") if t and len(t) > 2]
        ranking_keywords = _extract_rank_terms(query)

    # Use Grok for intelligent ranking based on semantic relevance
    reranked = await _grok_rank_tweets(
        tweets=items,
        highlighted_text=phrase,
        keywords=ranking_keywords,
        max_results=max_results
    )

    if not joiner:
        async with _cache_lock:
            _tweets_cache[key] = (time.time(), reranked)

    return SearchResponse(tweets=reranked, hints=hints)


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
        # also clear summary cache for this topic
        to_delete_s = [k for k in list(_summary_cache.keys()) if k.startswith(key_prefix)]
        for k in to_delete_s:
            _summary_cache.pop(k, None)
    return Response(status_code=204)


@app.get("/api/topics/{topic_slug}/tweets/summary")
async def get_topic_tweets_summary(topic_slug: str, max_results: int = 10) -> TweetsSummary:
    decoded_slug = unquote(topic_slug)
    phrase = decoded_slug.replace("_", " ").replace("-", " ").strip()
    if not phrase:
        raise HTTPException(status_code=400, detail="Empty topic slug")
    query = f'"{phrase}"'

    key = f"q={query}|n={max_results}"
    now = time.time()

    # Try cache first
    async with _cache_lock:
        if key in _summary_cache:
            ts, bullets = _summary_cache[key]
            if now - ts < SUMMARY_TTL_SECONDS:
                return TweetsSummary(bullets=bullets, model=_get_grok_model(), cached=True)
            else:
                _summary_cache.pop(key, None)

    # We need tweets first (use existing cache if warm)
    async with _cache_lock:
        cached = _tweets_cache.get(key)
    if cached:
        tweets = cached[1]
    else:
        tweets = await _fetch_recent_top_tweets(query=query, return_count=max_results)

    bullets = await _generate_tweets_summary(phrase, tweets)

    # Store in cache
    async with _cache_lock:
        _summary_cache[key] = (time.time(), bullets)

    return TweetsSummary(bullets=bullets, model=_get_grok_model(), cached=False)


# --- Dynamic Topic Endpoint (catch-all, must come LAST) ---

@app.get("/api/topics/{topic_slug:path}")
def get_topic(topic_slug: str) -> TopicDetail:
    """Get a specific topic by slug."""
    data = load_data()
    decoded_slug = unquote(topic_slug)

    for a in data:
        if extract_slug(a['url']) == decoded_slug:
            return TopicDetail(
                suggestion_count=get_suggestion_count(decoded_slug),
                topic=extract_slug(a['url']),
                title=a['title'],
                content=a['content']
            )
    raise HTTPException(status_code=404, detail="Topic not found")


# ---- Community Feed Helper Functions ----

def _get_x_bearer_token() -> Optional[str]:
    # Support either env var name
    return os.getenv("X_BEARER_TOKEN") or os.getenv("TWITTER_BEARER_TOKEN")


def _get_grok_api() -> Optional[str]:
    return os.getenv("GROK_API")


def _get_grok_base() -> str:
    return os.getenv("GROK_API_BASE", "https://api.x.ai/v1")


def _get_grok_model() -> str:
    return os.getenv("GROK_MODEL", "grok-2-latest")


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
    score = raw / norm if norm > 0 else raw
    # Apply a modest boost for verified accounts
    try:
        if user.get("verified"):
            score *= max(1.0, VERIFIED_BOOST)
    except Exception:
        pass
    return score


async def _fetch_recent_top_tweets(query: str, return_count: int = 10, pool_size: int = 50) -> list[TweetItem]:
    # Archive-first approach: try Search All for broader coverage; on 401/403 fallback to Recent.
    token = _get_x_bearer_token()
    if not token:
        raise HTTPException(status_code=501, detail="X API bearer token not configured. Set X_BEARER_TOKEN or TWITTER_BEARER_TOKEN.")

    all_url = "https://api.x.com/2/tweets/search/all"
    recent_url = "https://api.x.com/2/tweets/search/recent"

    params = {
        "query": f"{query} -is:retweet -is:reply lang:en",
        "max_results": str(max(10, min(pool_size, 100))),
        "sort_order": "relevancy",
        "tweet.fields": "public_metrics,created_at,lang,author_id",
        "expansions": "author_id",
        "user.fields": "username,name,profile_image_url,public_metrics,verified,verified_type",
    }
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # First, attempt Full-Archive Search
        use_recent_fallback = False
        try:
            r = await client.get(all_url, params=params, headers=headers)
            if r.status_code == 404:
                # Fallback domain
                r = await client.get("https://api.twitter.com/2/tweets/search/all", params=params, headers=headers)
            if r.status_code in (401, 403):
                use_recent_fallback = True
            else:
                r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code in (401, 403, 404):
                use_recent_fallback = True
            else:
                raise HTTPException(status_code=e.response.status_code if e.response else 502, detail=(e.response.text if e.response else str(e)))
        except httpx.RequestError as e:
            # Network problem on archive; try recent
            use_recent_fallback = True

        data = None
        if use_recent_fallback:
            try:
                r2 = await client.get(recent_url, params=params, headers=headers)
                if r2.status_code == 404:
                    r2 = await client.get("https://api.twitter.com/2/tweets/search/recent", params=params, headers=headers)
                r2.raise_for_status()
                data = r2.json()
            except httpx.HTTPStatusError as e:
                raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
            except httpx.RequestError as e:
                raise HTTPException(status_code=502, detail=f"Failed to reach X API: {e}")
        else:
            data = r.json()

        tweets = data.get("data", []) or []
        includes = data.get("includes", {}) or {}
        users = {u.get("id"): u for u in includes.get("users", [])}

        ranked: list[tuple[float, dict, dict]] = []
        for t in tweets:
            u = users.get(t.get("author_id")) if t.get("author_id") else None
            score = _compute_score(t, u or {})
            ranked.append((score, t, u or {}))

        if not ranked:
            return []

        ranked.sort(key=lambda x: x[0], reverse=True)
        ranked = ranked[:max(1, return_count * 2)]
        out: list[TweetItem] = []
        now_dt = datetime.now(timezone.utc)
        for idx, (score, t, u) in enumerate(ranked[:return_count]):
            tid = t.get("id")
            text = t.get("text", "")
            created_at = t.get("created_at")
            metrics = t.get("public_metrics", {}) or {}
            username = (u or {}).get("username")
            name = (u or {}).get("name")
            pfp = (u or {}).get("profile_image_url")
            verified = (u or {}).get("verified")
            verified_type = (u or {}).get("verified_type")
            url = f"https://x.com/{username}/status/{tid}" if username and tid else f"https://x.com/i/web/status/{tid}"
            # trending flag: recent within TRENDING_HOURS and ranked within top-K
            is_recent = False
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    is_recent = (now_dt - dt) <= timedelta(hours=TRENDING_HOURS)
                except Exception:
                    is_recent = False
            # Trending preview override (rank-based, regardless of recency)
            rank1 = idx + 1
            preview_trend = (TRENDING_PREVIEW_TOP_K > 0 and idx < TRENDING_PREVIEW_TOP_K) or (rank1 in TRENDING_PREVIEW_RANKS)
            is_trending = bool(preview_trend or (is_recent and (idx < max(1, TRENDING_TOP_K))))
            out.append(
                TweetItem(
                    id=tid,
                    text=text,
                    author_username=username or "",
                    author_name=name,
                    author_profile_image_url=pfp,
                    author_verified=bool(verified) if verified is not None else None,
                    author_verified_type=verified_type,
                    created_at=created_at,
                    like_count=metrics.get("like_count"),
                    retweet_count=metrics.get("retweet_count"),
                    reply_count=metrics.get("reply_count"),
                    quote_count=metrics.get("quote_count"),
                    url=url,
                    score=score,
                    trending=is_trending,
                )
            )
        return out


async def _generate_tweets_summary(topic_phrase: str, tweets: List[TweetItem]) -> List[str]:
    token = _get_grok_api()
    if not token:
        raise HTTPException(status_code=501, detail="Grok API key not configured. Set GROK_API in root .env.")

    base = _get_grok_base().rstrip("/")
    model = _get_grok_model()
    url = f"{base}/chat/completions"

    # Use top-of-top tweets (first 5) for summary context
    top_context = tweets[:5]
    context_lines = []
    for i, t in enumerate(top_context, start=1):
        context_lines.append(
            f"{i}. {t.text}\n   by @{t.author_username} | ❤ {t.like_count or 0} ↻ {t.retweet_count or 0} 💬 {t.reply_count or 0}"
        )
    context_block = "\n".join(context_lines) if context_lines else "(no tweets)"

    system_prompt = (
        "You are an expert social media curator. Summarize the most important takeaways from the topic's top tweets in 2-3 concise bullets."
        " Be neutral, non-promotional, and avoid links or hashtags. Focus on key themes, insights, or consensus."
    )

    user_prompt = (
        f"Topic: {topic_phrase}\n\nTop tweets (ordered by engagement):\n{context_block}\n\n"
        "Return ONLY a compact JSON array of 2-3 short bullet strings. Do not include any extra keys or text."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # Encourage json-like behavior; different Grok deployments may ignore, that's fine
        "temperature": 0.2,
        "max_tokens": 256,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to reach Grok API: {e}")

    data = resp.json()

    # Try to parse content as a JSON array
    content = None
    try:
        # OpenAI-style response structure compatibility
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
    except Exception:
        content = None

    bullets: List[str] = []
    if isinstance(content, str):
        # Extract JSON array from content
        try:
            # Find first [ and last ] to be robust to minor pre/post text
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end != -1 and end > start:
                import json as _json
                arr = _json.loads(content[start: end + 1])
                if isinstance(arr, list):
                    bullets = [str(x) for x in arr][:3]
        except Exception:
            bullets = []

    # Ensure we return up to 3 compact bullets
    bullets = [b.strip() for b in bullets if isinstance(b, str) and b.strip()][:3]
    return bullets
def get_factual_label(score: float) -> str:
    """Map factual reporting score (0-10, lower is better) to label."""
    if score <= 1.0:
        return "Very High"
    elif score <= 2.5:
        return "High"
    elif score <= 4.0:
        return "Mostly Factual"
    elif score <= 6.0:
        return "Mixed"
    elif score <= 8.0:
        return "Low"
    else:
        return "Very Low"


def get_bias_label(score: float) -> str:
    """Map bias score (-10 to +10) to label. Negative = Left, Positive = Right, Near 0 = Center."""
    if score <= -7.5:
        return "Extreme Left"
    elif score <= -3.5:
        return "Left"
    elif score <= -1.0:
        return "Left-Center"
    elif score < 1.0:
        return "Center"
    elif score < 3.5:
        return "Right-Center"
    elif score < 7.5:
        return "Right"
    else:
        return "Extreme Right"


def extract_citations_from_content(content: str) -> list[str]:
    """Extract all URLs from markdown content (both [text](url) and [](url) formats)."""
    # Match markdown links: [optional text](url)
    pattern = r'\[(?:[^\]]*)\]\(([^)]+)\)'
    urls = re.findall(pattern, content)
    # Filter to only http/https URLs and deduplicate while preserving order
    seen = set()
    result = []
    for url in urls:
        if url.startswith(('http://', 'https://')) and url not in seen:
            seen.add(url)
            result.append(url)
    return result


@app.get("/api/aggregate_bias/{topic_slug:path}")
def aggregate_bias(topic_slug: str, version_index: int | None = None) -> AggregateBiasResponse:
    """Get aggregated bias and factual reporting data for an article's citations.

    Args:
        topic_slug: The article slug
        version_index: Optional version index. If provided, extracts citations from that version's content.
    """
    # Load articles
    data = load_data()
    decoded_slug = unquote(topic_slug)

    # Find the article
    article = None
    for a in data:
        if extract_slug(a['url']) == decoded_slug:
            article = a
            break

    if not article:
        raise HTTPException(status_code=404, detail="Topic not found")

    article_title = article.get('title', '')
    article_url = article.get('url', '')

    # Get citations based on version
    if version_index is not None:
        # Get citations from specific version's content
        versions = article.get('versions', [])
        if version_index < 0 or version_index >= len(versions):
            raise HTTPException(status_code=404, detail="Version not found")
        version_content = versions[version_index].get('content', '')
        citations = extract_citations_from_content(version_content)
    else:
        # Use current article citations (or extract from current content as fallback)
        citations = article.get('citations', [])
        if not citations:
            # Fallback: extract from current content
            citations = extract_citations_from_content(article.get('content', ''))
    
    if not citations:
        raise HTTPException(
            status_code=404,
            detail="Article has no citations"
        )
    
    # Load citation evaluations (now a dict with URLs as keys)
    try:
        with open(CITATION_EVALUATIONS_FILE, 'r', encoding='utf-8') as f:
            evaluations = json.load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Citation evaluations file not found"
        )
    
    # Match citations to evaluations and collect scores
    factual_scores = []
    bias_scores = []
    
    for citation_url in citations:
        if citation_url in evaluations:
            eval_entry = evaluations[citation_url]
            eval_data = eval_entry.get('evaluation', {})
            article_eval = eval_data.get('article', {})
            
            factual = article_eval.get('factual_reporting', {})
            bias_data = article_eval.get('bias', {})
            
            if 'overall_score' in factual:
                factual_scores.append(factual['overall_score'])
            if 'overall_score' in bias_data:
                bias_scores.append(bias_data['overall_score'])
    
    if not factual_scores and not bias_scores:
        raise HTTPException(
            status_code=404,
            detail="No evaluated citations found for this article"
        )
    
    # Calculate averages
    avg_factual = sum(factual_scores) / len(factual_scores) if factual_scores else 0.0
    avg_bias = sum(bias_scores) / len(bias_scores) if bias_scores else 0.0
    
    # Get labels
    factual_label = get_factual_label(avg_factual)
    bias_label = get_bias_label(avg_bias)
    
    return AggregateBiasResponse(
        article_title=article_title,
        article_url=article_url,
        citation_count=len(citations),
        evaluated_citation_count=len(factual_scores),
        average_factual_score=round(avg_factual, 1),
        factual_label=factual_label,
        average_bias_score=round(avg_bias, 1),
        bias_label=bias_label
    )


# --- Article Preview Endpoint ---

class ArticlePreview(BaseModel):
    url: str
    title: str
    content: str
    domain: str
    error: str | None = None


@app.get("/api/fetch-article")
async def fetch_article(url: str) -> ArticlePreview:
    """Fetch and extract readable content from a URL."""
    # Parse domain from URL
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or "unknown"
    except Exception:
        domain = "unknown"

    # Validate URL
    if not url.startswith(("http://", "https://")):
        return ArticlePreview(
            url=url,
            title="Invalid URL",
            content="",
            domain=domain,
            error="URL must start with http:// or https://"
        )

    try:
        # Fetch the page
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)
        else:
            title = domain

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]):
            tag.decompose()

        # Try to find main content
        main_content = None
        for selector in ["article", "main", '[role="main"]', ".post-content", ".article-content", ".entry-content"]:
            main_content = soup.select_one(selector)
            if main_content:
                break

        # Fall back to body if no main content found
        if not main_content:
            main_content = soup.body if soup.body else soup

        # Convert to markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.ignore_emphasis = False
        h.body_width = 0  # Don't wrap lines
        h.skip_internal_links = True

        content = h.handle(str(main_content))

        # Clean up excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content).strip()

        # Limit content length to prevent huge responses
        max_length = 50000
        if len(content) > max_length:
            content = content[:max_length] + "\n\n... (content truncated)"

        return ArticlePreview(
            url=url,
            title=title,
            content=content,
            domain=domain
        )

    except httpx.TimeoutException:
        return ArticlePreview(
            url=url,
            title="Request Timeout",
            content="",
            domain=domain,
            error="The request timed out. The website may be slow or unavailable."
        )
    except httpx.HTTPStatusError as e:
        return ArticlePreview(
            url=url,
            title=f"HTTP Error {e.response.status_code}",
            content="",
            domain=domain,
            error=f"Failed to fetch the page: HTTP {e.response.status_code}"
        )
    except Exception as e:
        return ArticlePreview(
            url=url,
            title="Error",
            content="",
            domain=domain,
            error=f"Failed to fetch or parse the article: {str(e)}"
        )


@app.get("/api/citation_bias")
def get_citation_bias(url: str) -> CitationBiasResponse:
    """Get bias and factual reporting data for a specific citation URL."""
    from urllib.parse import unquote
    
    # Load citation evaluations
    try:
        with open(CITATION_EVALUATIONS_FILE, 'r', encoding='utf-8') as f:
            evaluations = json.load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Citation evaluations file not found"
        )
    
    # Normalize URL: decode URL encoding and try to match
    # First try exact match
    normalized_url = unquote(url).rstrip('/')
    original_url = url.rstrip('/')
    
    # Try multiple variations
    url_variants = [
        url,
        normalized_url,
        original_url,
        url.rstrip('/'),
        normalized_url.rstrip('/'),
    ]
    
    eval_entry = None
    matched_url = None
    
    for variant in url_variants:
        if variant in evaluations:
            eval_entry = evaluations[variant]
            matched_url = variant
            break
    
    if not eval_entry:
        # Try case-insensitive and with/without trailing slash
        url_lower = url.lower()
        for key in evaluations.keys():
            if key.lower() == url_lower or key.lower().rstrip('/') == url_lower.rstrip('/'):
                eval_entry = evaluations[key]
                matched_url = key
                break
    
    if not eval_entry:
        raise HTTPException(
            status_code=404,
            detail=f"Citation not found or not evaluated. Tried: {url}"
        )
    
    eval_data = eval_entry.get('evaluation', {})
    article_eval = eval_data.get('article', {})
    
    factual = article_eval.get('factual_reporting', {})
    bias_data = article_eval.get('bias', {})
    
    factual_score = factual.get('overall_score', 0.0)
    bias_score = bias_data.get('overall_score', 0.0)
    
    factual_label = get_factual_label(factual_score)
    bias_label = get_bias_label(bias_score)
    
    return CitationBiasResponse(
        citation_url=matched_url or url,
        factual_score=round(factual_score, 1),
        factual_label=factual_label,
        bias_score=round(bias_score, 1),
        bias_label=bias_label
    )


# --- Article Summary Endpoint ---

class SummaryRequest(BaseModel):
    content: str
    title: str | None = None


class SummaryResponse(BaseModel):
    summary: str
    error: str | None = None


@app.post("/api/summarize-preview")
async def summarize_preview(request: SummaryRequest) -> SummaryResponse:
    """Generate a Grok summary of article content."""
    if not request.content or len(request.content.strip()) < 50:
        return SummaryResponse(
            summary="",
            error="Content too short to summarize"
        )

    # Truncate content if too long (keep first ~8000 chars for context)
    content = request.content[:8000]
    title_context = f'Article: "{request.title}"\n\n' if request.title else ""

    system_prompt = """You are Grokipedia's article summarizer. Your task is to provide clear, informative summaries that help readers quickly understand the key points of an article.

Guidelines:
- Write 2-3 concise sentences capturing the main points
- Focus on facts, key findings, or central arguments
- Use neutral, encyclopedic tone
- Don't start with "This article..." or "The article..."
- Go straight to the substance"""

    user_prompt = f"""{title_context}Summarize the following article content:

{content}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GROK_API_KEY}"
                },
                json={
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "model": "grok-3-fast-latest",
                    "temperature": 0.3,
                    "max_tokens": 200
                }
            )
            response.raise_for_status()
            result = response.json()

        summary = result["choices"][0]["message"]["content"].strip()
        return SummaryResponse(summary=summary)

    except httpx.TimeoutException:
        return SummaryResponse(
            summary="",
            error="Summary request timed out"
        )
    except Exception as e:
        return SummaryResponse(
            summary="",
            error=f"Failed to generate summary: {str(e)}"
        )
