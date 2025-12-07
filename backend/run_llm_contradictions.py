"""
Call the x.ai API to detect contradictions within each multi-article cluster.

Inputs:
  - clusters.json (produced by cluster_articles.py)
  - all_articles_short.json (source articles with url/title/content)

Outputs:
  - contradictions_llm.json : list of results per cluster with parsed contradictions and offsets

Usage:
  XAI_API_KEY=... python run_llm_contradictions.py

Notes:
  - Skips clusters of size 1.
  - Sends trimmed excerpts (title + first N chars of content) to keep prompt small.
  - Asks the model to return JSON. We post-process to locate quoted claims in the text
    and record offsets/line numbers for UI highlighting.
"""

import json
import os
from pathlib import Path
from typing import Dict, List

import requests


CLUSTERS_FILE = Path(__file__).parent / "clusters.json"
ARTICLES_FILE = Path(__file__).parent / "all_articles_short.json"
OUTPUT_FILE = Path(__file__).parent / "contradictions_llm.json"
# Use grok-4-1-fast-reasoning with reasoning effort (matches working notebook)
MODEL = os.environ.get("XAI_MODEL", "grok-4-1-fast-reasoning")
REASONING_EFFORT = os.environ.get("XAI_REASONING_EFFORT", "high")
MAX_ARTICLE_CHARS = 1600  # trim each article to keep prompt size reasonable
TIMEOUT_SECONDS = 300  # reasoning models can take longer


def load_articles() -> Dict[str, Dict[str, str]]:
    data = json.loads(ARTICLES_FILE.read_text())
    by_url: Dict[str, Dict[str, str]] = {}
    for item in data:
        by_url[item["url"]] = {
            "title": item.get("title", ""),
            "content": item.get("content", ""),
        }
    return by_url


def load_clusters() -> List[Dict]:
    return json.loads(CLUSTERS_FILE.read_text())


def trim_content(text: str, limit: int = MAX_ARTICLE_CHARS) -> str:
    return text[:limit]


def build_messages(cluster: Dict, articles_by_url: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    articles = []
    for m in cluster["members"]:
        url = m["url"]
        art = articles_by_url.get(url, {"title": m.get("title", ""), "content": ""})
        articles.append(
            {
                "title": art.get("title", ""),
                "url": url,
                "content": trim_content(art.get("content", "")),
            }
        )

    articles_block = "\n\n".join(
        [f"[{idx+1}] Title: {a['title']}\nURL: {a['url']}\nContent:\n{a['content']}" for idx, a in enumerate(articles)]
    )

    system_prompt = (
        "You are a careful editor.\n"
        "Find factual contradictions between the provided articles only. Do not invent info beyond what is given.\n"
        "Prioritize differences in numbers, counts, dates, rankings, names, spellings, affiliations, or leagues.\n"
        "If no contradictions, return an empty list."
    )

    user_prompt = (
        "Articles:\n"
        f"{articles_block}\n\n"
        "Task: List contradictions as pairs. For each contradiction, include:\n"
        "- article_a_title, article_a_url\n"
        "- claim_a: EXACT quote copied directly from article content (do not paraphrase or summarize)\n"
        "- article_b_title, article_b_url\n"
        "- claim_b: EXACT quote copied directly from article content (do not paraphrase or summarize)\n"
        "- difference: short phrase of what differs\n\n"
        "CRITICAL: claim_a and claim_b must be EXACT substring matches from the Content field above.\n"
        "Copy the exact phrase character-for-character, including punctuation and spacing.\n"
        "Return a JSON list."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def call_xai(messages: List[Dict[str, str]], api_key: str) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "reasoning": {"effort": REASONING_EFFORT},  # matches working notebook
    }
    resp = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json=payload,
        timeout=TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    parsed = resp.json()
    return parsed["choices"][0]["message"]["content"]


def find_offset(content: str, snippet: str) -> Dict[str, int]:
    """
    Best-effort find snippet in content. Returns start/end offsets and line (1-based).
    """
    start = content.find(snippet)
    if start == -1:
        return {"start": -1, "end": -1, "line": -1}
    end = start + len(snippet)
    line = content.count("\n", 0, start) + 1
    return {"start": start, "end": end, "line": line}


def parse_llm_response(content: str, cluster: Dict, articles_by_url: Dict[str, Dict[str, str]]) -> Dict:
    """
    Try to parse the LLM JSON; enrich with offsets. On failure, return raw.
    """
    try:
        data = json.loads(content)
        if not isinstance(data, list):
            raise ValueError("expected list")
    except Exception:
        return {"raw": content}

    by_url_fulltext = {
        m["url"]: trim_content(articles_by_url.get(m["url"], {}).get("content", ""))
        for m in cluster["members"]
    }

    enriched = []
    for item in data:
        a_url = item.get("article_a_url", "")
        b_url = item.get("article_b_url", "")
        claim_a = item.get("claim_a", "")
        claim_b = item.get("claim_b", "")
        a_text = by_url_fulltext.get(a_url, "")
        b_text = by_url_fulltext.get(b_url, "")
        a_off = find_offset(a_text, claim_a) if claim_a else {"start": -1, "end": -1, "line": -1}
        b_off = find_offset(b_text, claim_b) if claim_b else {"start": -1, "end": -1, "line": -1}
        enriched.append(
            {
                "article_a_title": item.get("article_a_title", ""),
                "article_a_url": a_url,
                "claim_a": claim_a,
                "claim_a_offset": a_off,
                "article_b_title": item.get("article_b_title", ""),
                "article_b_url": b_url,
                "claim_b": claim_b,
                "claim_b_offset": b_off,
                "difference": item.get("difference", ""),
            }
        )
    return {"contradictions": enriched}


def main() -> None:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set XAI_API_KEY in the environment")

    articles_by_url = load_articles()
    clusters = load_clusters()

    # Run LLM calls in parallel (I/O bound)
    import concurrent.futures

    def process_cluster(cluster: Dict) -> Dict:
        messages = build_messages(cluster, articles_by_url)
        try:
            content = call_xai(messages, api_key)
        except Exception as e:
            content = f"ERROR: {e}"
        parsed = parse_llm_response(content, cluster, articles_by_url)
        return {
            "cluster_id": cluster["cluster_id"],
            "size": cluster["size"],
            "members": cluster["members"],
            "llm_response": content,
            "parsed": parsed,
        }

    to_process = [c for c in clusters if c.get("size", 0) > 1]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(process_cluster, to_process):
            results.append(res)

    OUTPUT_FILE.write_text(json.dumps(results, indent=2))
    print(f"[done] wrote {len(results)} cluster results to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

