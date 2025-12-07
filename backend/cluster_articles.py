import json
import math
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


DATA_FILE = Path(__file__).parent / "all_articles_short.json"
OUTPUT_FILE = Path(__file__).parent / "clusters.json"


_sent_split = re.compile(r"(?<=[.!?])\s+")
_numeric_re = re.compile(r"(\d|\%|million|billion|th\b|st\b|nd\b|rd\b)", re.IGNORECASE)
_punct_tbl = str.maketrans({p: " " for p in string.punctuation})
_generic_tokens = {
    "population",
    "economy",
    "geography",
    "history",
    "demographics",
    "politics",
    "culture",
    "overview",
    "transport",
    "transportation",
    "list",
    "state",
    "country",
    "city",
    "province",
    "region",
}
_min_token_len = 3
_stop_words = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "these",
    "those",
    "into",
    "over",
    "under",
    "between",
    "within",
    "into",
    "about",
    "around",
    "across",
    "near",
    "at",
    "by",
    "in",
    "on",
    "of",
    "to",
    "as",
    "an",
    "a",
    "is",
    "are",
    "be",
    "was",
    "were",
    "it",
    "its",
    "their",
    "his",
    "her",
    "them",
    "they",
    "he",
    "she",
    "we",
    "you",
    "your",
}


@dataclass
class Article:
    url: str
    title: str
    content: str


def load_articles() -> List[Article]:
    with open(DATA_FILE) as f:
        raw = json.load(f)
    articles: List[Article] = []
    for item in raw:
        articles.append(
            Article(
                url=item.get("url", ""),
                title=item.get("title", ""),
                content=item.get("content", ""),
            )
        )
    return articles


def slug_from_url(url: str) -> str:
    slug = url.split("/page/")[-1] if "/page/" in url else url
    return slug


def slug_tokens(slug: str) -> List[str]:
    slug = slug.replace("_", " ").replace("-", " ")
    cleaned = slug.translate(_punct_tbl).lower()
    tokens = cleaned.split()
    return [t for t in tokens if t and t not in _generic_tokens and len(t) >= _min_token_len and any(ch.isalpha() for ch in t)]


def normalize_tokens(text: str) -> List[str]:
    cleaned = text.translate(_punct_tbl).lower()
    tokens = []
    for t in cleaned.split():
        if not t:
            continue
        if len(t) < _min_token_len:
            continue
        if not any(ch.isalpha() for ch in t):
            continue
        if t in _stop_words:
            continue
        tokens.append(t)
    return tokens


def split_sentences(text: str) -> List[str]:
    parts = _sent_split.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def pick_numeric_sentences(sentences: List[str], limit: int = 5) -> List[str]:
    picked = []
    for s in sentences:
        if _numeric_re.search(s):
            picked.append(s)
        if len(picked) >= limit:
            break
    return picked


def build_trimmed_text(article: Article) -> str:
    # Lead paragraph: first block before a blank line or first 3 sentences.
    paragraphs = [p for p in article.content.split("\n\n") if p.strip()]
    lead = paragraphs[0] if paragraphs else article.content
    sentences = split_sentences(article.content)
    numeric_sents = pick_numeric_sentences(sentences, limit=5)
    parts = [
        article.title,
        lead,
        "\n".join(numeric_sents),
    ]
    return "\n".join([p for p in parts if p])


def build_vocab_and_tfidf(docs_tokens: List[List[str]], top_k: int = 10) -> List[Dict[str, float]]:
    # Add bigrams to capture short names
    docs_with_ngrams: List[List[str]] = []
    for tokens in docs_tokens:
        bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
        docs_with_ngrams.append(tokens + bigrams)
    docs_tokens = docs_with_ngrams

    # Document frequencies
    df: Dict[str, int] = {}
    for tokens in docs_tokens:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1

    N = len(docs_tokens)

    tfidf_docs: List[Dict[str, float]] = []
    for tokens in docs_tokens:
        tf: Dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        weights: Dict[str, float] = {}
        for t, count in tf.items():
            idf = math.log((N + 1) / (df[t] + 1)) + 1.0
            weights[t] = count * idf
        # keep top_k terms
        top = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:top_k]
        tfidf_docs.append({t: w for t, w in top})
    return tfidf_docs


def build_char_tfidf(texts: List[str], n_min: int = 3, n_max: int = 5, top_k: int = 25) -> List[Dict[str, float]]:
    grams_list: List[List[str]] = []
    df: Dict[str, int] = {}
    for txt in texts:
        grams = []
        cleaned = txt.lower()
        cleaned = re.sub(r"\s+", " ", cleaned)
        for n in range(n_min, n_max + 1):
            for i in range(len(cleaned) - n + 1):
                g = cleaned[i : i + n]
                grams.append(g)
        grams_list.append(grams)
        for g in set(grams):
            df[g] = df.get(g, 0) + 1

    N = len(texts)
    tfidf_docs: List[Dict[str, float]] = []
    for grams in grams_list:
        tf: Dict[str, int] = {}
        for g in grams:
            tf[g] = tf.get(g, 0) + 1
        weights: Dict[str, float] = {}
        for g, count in tf.items():
            idf = math.log((N + 1) / (df[g] + 1)) + 1.0
            weights[g] = count * idf
        top = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:top_k]
        tfidf_docs.append({g: w for g, w in top})
    return tfidf_docs


def cosine_dict(a: Dict[str, float], b: Dict[str, float]) -> float:
    shared = set(a.keys()) & set(b.keys())
    if not shared:
        return 0.0
    num = sum(a[t] * b[t] for t in shared)
    denom = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / denom if denom else 0.0


def edit_distance(s1: str, s2: str, max_dist: int = 2) -> int:
    # Simple Levenshtein with early stop
    if abs(len(s1) - len(s2)) > max_dist:
        return max_dist + 1
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1, 1):
        curr = [i]
        min_row = curr[0]
        for j, c2 in enumerate(s2, 1):
            cost = 0 if c1 == c2 else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
            if curr[j] < min_row:
                min_row = curr[j]
        if min_row > max_dist:
            return max_dist + 1
        prev = curr
    return prev[-1]


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            self.parent[rx] = ry
        elif self.rank[rx] > self.rank[ry]:
            self.parent[ry] = rx
        else:
            self.parent[ry] = rx
            self.rank[rx] += 1


def cluster_articles(articles: List[Article]) -> List[List[int]]:
    slugs = [slug_from_url(a.url) for a in articles]
    slug_tok_sets = [set(slug_tokens(s)) for s in slugs]
    trimmed = [build_trimmed_text(a) for a in articles]
    doc_tokens = [normalize_tokens(text) for text in trimmed]
    tfidf_docs = build_vocab_and_tfidf(doc_tokens, top_k=15)
    top_terms_per_doc = [set(d.keys()) for d in tfidf_docs]
    char_tfidf_docs = build_char_tfidf(trimmed, top_k=25)

    uf = UnionFind(len(articles))

    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            sim = cosine_dict(tfidf_docs[i], tfidf_docs[j])
            sim_char = cosine_dict(char_tfidf_docs[i], char_tfidf_docs[j])

            slug_overlap = slug_tok_sets[i] & slug_tok_sets[j]
            has_specific_slug = any(t not in _generic_tokens for t in slug_overlap)
            title_tokens_i = set(normalize_tokens(articles[i].title))
            title_tokens_j = set(normalize_tokens(articles[j].title))
            shared_title_tokens = title_tokens_i & title_tokens_j
            title_jaccard = (
                len(shared_title_tokens) / len(title_tokens_i | title_tokens_j)
                if title_tokens_i and title_tokens_j
                else 0
            )
            rare_overlap = top_terms_per_doc[i] & top_terms_per_doc[j]
            shared_meaningful = (slug_tok_sets[i] | title_tokens_i) & (slug_tok_sets[j] | title_tokens_j)

            gate = False
            if not shared_meaningful:
                continue  # avoid merging symbol/empty titles

            if (has_specific_slug or title_jaccard >= 0.5) and sim >= 0.20:
                gate = True
            elif len(rare_overlap) >= 2 and sim >= 0.30:
                gate = True
            elif title_jaccard >= 0.6 and sim >= 0.20:
                gate = True
            elif sim >= 0.35 and sim_char >= 0.25 and len(rare_overlap) >= 1:
                gate = True

            if gate:
                uf.union(i, j)

    clusters = {}
    for idx in range(len(articles)):
        root = uf.find(idx)
        clusters.setdefault(root, []).append(idx)

    # Split oversized clusters if any (unlikely for 100 docs)
    final_clusters: List[List[int]] = []
    for members in clusters.values():
        if len(members) <= 200:
            final_clusters.append(members)
        else:
            # naive split: keep as singletons to avoid over-merge
            final_clusters.extend([[m] for m in members])

    return final_clusters


def serialize_clusters(clusters: List[List[int]], articles: List[Article]) -> List[dict]:
    output = []
    for cid, members in enumerate(clusters):
        output.append(
            {
                "cluster_id": cid,
                "size": len(members),
                "members": [
                    {
                        "url": articles[i].url,
                        "title": articles[i].title,
                        "slug": slug_from_url(articles[i].url),
                    }
                    for i in members
                ],
            }
        )
    return output


def main() -> None:
    articles = load_articles()
    clusters = cluster_articles(articles)
    serialized = serialize_clusters(clusters, articles)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(serialized, f, indent=2)
    print(f"[done] wrote {len(serialized)} clusters to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

