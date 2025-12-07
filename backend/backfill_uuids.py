#!/usr/bin/env python3
"""
Script to backfill all articles with UUIDs under the "id" field.
Preserves existing data and only adds UUIDs if they don't exist.
"""

import json
import uuid
from pathlib import Path

# Paths
DATA_FILE = Path(__file__).parent / "all_articles_short.json"


def backfill_uuids():
    """Add UUIDs to all articles that don't have them."""
    print(f"Loading articles from {DATA_FILE}...")
    
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    print(f"Loaded {len(articles)} articles")
    
    updated_count = 0
    for article in articles:
        if 'id' not in article or not article.get('id'):
            article['id'] = str(uuid.uuid4())
            updated_count += 1
    
    if updated_count == 0:
        print("All articles already have UUIDs.")
        return
    
    print(f"Adding UUIDs to {updated_count} articles...")
    
    # Save updated articles
    print(f"Saving updated articles to {DATA_FILE}...")
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)
    
    print(f"Done! Added UUIDs to {updated_count} articles.")
    print(f"Total articles: {len(articles)}")


if __name__ == "__main__":
    backfill_uuids()

