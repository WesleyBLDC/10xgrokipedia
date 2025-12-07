import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

DATA_FILE = Path(__file__).parent / "all_articles_short.json"
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
