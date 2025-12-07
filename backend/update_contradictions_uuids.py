#!/usr/bin/env python3
"""
Update contradictions_llm.json to use UUIDs instead of slugs in URLs.
"""

import json
from pathlib import Path

ARTICLES_FILE = Path(__file__).parent / "all_articles_short.json"
CONTRADICTIONS_FILE = Path(__file__).parent / "contradictions_llm.json"


def load_articles() -> dict:
    """Load articles and create a mapping from URL to UUID."""
    print(f"Loading articles from {ARTICLES_FILE}...")
    with open(ARTICLES_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    # Create mapping: URL -> UUID
    url_to_uuid = {}
    for article in articles:
        url = article.get('url', '')
        article_id = article.get('id', '')
        if url and article_id:
            url_to_uuid[url] = article_id
    
    print(f"Loaded {len(articles)} articles, {len(url_to_uuid)} with URLs and UUIDs")
    return url_to_uuid


def update_url_to_uuid(url: str, url_to_uuid: dict) -> str:
    """Convert a URL to use UUID instead of slug."""
    if not url.startswith('https://grokipedia.com/page/'):
        return url  # Not a grokipedia URL, return as-is
    
    # Extract the slug part
    slug = url.replace('https://grokipedia.com/page/', '')
    
    # Find the UUID for this URL
    uuid = url_to_uuid.get(url)
    if uuid:
        return f"https://grokipedia.com/page/{uuid}"
    else:
        print(f"Warning: No UUID found for URL: {url}")
        return url  # Return original if no UUID found


def update_contradictions(url_to_uuid: dict):
    """Update contradictions file to use UUIDs in URLs."""
    print(f"\nLoading contradictions from {CONTRADICTIONS_FILE}...")
    with open(CONTRADICTIONS_FILE, 'r', encoding='utf-8') as f:
        contradictions = json.load(f)
    
    updated_count = 0
    not_found_count = 0
    
    for cluster in contradictions:
        # Update member URLs
        for member in cluster.get('members', []):
            old_url = member.get('url', '')
            if old_url:
                new_url = update_url_to_uuid(old_url, url_to_uuid)
                if new_url != old_url:
                    member['url'] = new_url
                    updated_count += 1
                elif old_url.startswith('https://grokipedia.com/page/'):
                    not_found_count += 1
        
        # Update contradiction URLs
        parsed = cluster.get('parsed', {})
        contradictions_list = parsed.get('contradictions', [])
        for contradiction in contradictions_list:
            # Update article_a_url
            old_url_a = contradiction.get('article_a_url', '')
            if old_url_a:
                new_url_a = update_url_to_uuid(old_url_a, url_to_uuid)
                if new_url_a != old_url_a:
                    contradiction['article_a_url'] = new_url_a
                    updated_count += 1
                elif old_url_a.startswith('https://grokipedia.com/page/'):
                    not_found_count += 1
            
            # Update article_b_url
            old_url_b = contradiction.get('article_b_url', '')
            if old_url_b:
                new_url_b = update_url_to_uuid(old_url_b, url_to_uuid)
                if new_url_b != old_url_b:
                    contradiction['article_b_url'] = new_url_b
                    updated_count += 1
                elif old_url_b.startswith('https://grokipedia.com/page/'):
                    not_found_count += 1
    
    print(f"\nUpdated {updated_count} URLs")
    if not_found_count > 0:
        print(f"Warning: {not_found_count} URLs could not be found in articles")
    
    # Write back to file
    print(f"\nWriting updated contradictions to {CONTRADICTIONS_FILE}...")
    with open(CONTRADICTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(contradictions, f, indent=2, ensure_ascii=False)
    
    print("Done!")


def main():
    url_to_uuid = load_articles()
    update_contradictions(url_to_uuid)


if __name__ == '__main__':
    main()

