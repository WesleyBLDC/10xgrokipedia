import json
from pathlib import Path
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

DATA_FILE = Path(__file__).parent / "temp_data.json"


class Topic(BaseModel):
    topic: str
    title: str
    description: str


def load_data() -> list[Topic]:
    with open(DATA_FILE) as f:
        return [Topic(**item) for item in json.load(f)]


@app.get("/api/topics")
def get_topics() -> list[dict]:
    """Get all topics (for search)."""
    data = load_data()
    return [{"topic": t.topic, "title": t.title} for t in data]


@app.get("/api/topics/search")
def search_topics(q: str = "") -> list[dict]:
    """Search topics by query string."""
    data = load_data()
    query = q.lower()
    results = [
        {"topic": t.topic, "title": t.title}
        for t in data
        if query in t.title.lower() or query in t.topic.lower()
    ]
    return results


@app.get("/api/topics/{topic_slug}")
def get_topic(topic_slug: str) -> Topic:
    """Get a specific topic by slug."""
    data = load_data()
    for t in data:
        if t.topic == topic_slug:
            return t
    raise HTTPException(status_code=404, detail="Topic not found")
