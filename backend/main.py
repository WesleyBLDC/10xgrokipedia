import json
from pathlib import Path
from urllib.parse import unquote
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="10xGrokipedia API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = Path(__file__).parent / "all_articles_short.json"


class Article(BaseModel):
    url: str
    title: str
    content: str


class TopicSummary(BaseModel):
    topic: str
    title: str


class TopicDetail(BaseModel):
    topic: str
    title: str
    content: str


def extract_slug(url: str) -> str:
    """Extract topic slug from Grokipedia URL."""
    # URL format: https://grokipedia.com/page/Topic_Name
    return url.split("/page/")[-1] if "/page/" in url else url


def load_data() -> list[Article]:
    with open(DATA_FILE) as f:
        return [Article(**item) for item in json.load(f)]


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


@app.get("/api/topics/{topic_slug:path}")
def get_topic(topic_slug: str) -> TopicDetail:
    """Get a specific topic by slug."""
    data = load_data()
    # Decode URL-encoded slugs (e.g., %20 -> space)
    decoded_slug = unquote(topic_slug)

    for a in data:
        if extract_slug(a.url) == decoded_slug:
            return TopicDetail(
                topic=extract_slug(a.url),
                title=a.title,
                content=a.content
            )
    raise HTTPException(status_code=404, detail="Topic not found")
