#!/usr/bin/env python3
"""
Script to extract all citations from articles and add them to a 'citations' attribute.
Citations are extracted from markdown links like [](url) and deduplicated.
"""

import json
import re
from pathlib import Path
from typing import List, Set

# Paths
DATA_FILE = Path(__file__).parent / "all_articles_short.json"


def extract_citation_urls(content: str) -> List[str]:
    """Extract all citation URLs from markdown content."""
    urls = []
    
    # Pattern to match markdown links: [](url) or [text](url)
    link_pattern = r'\[([^\]]*)\]\(([^)]+)\)'
    
    for match in re.finditer(link_pattern, content):
        url = match.group(2)
        # Only include external URLs (http/https)
        if url.startswith('http://') or url.startswith('https://'):
            urls.append(url)
    
    return urls


def deduplicate_citations(citations: List[str]) -> List[str]:
    """Remove duplicate citations while preserving order."""
    seen: Set[str] = set()
    unique: List[str] = []
    
    for citation in citations:
        if citation not in seen:
            seen.add(citation)
            unique.append(citation)
    
    return unique


def main():
    """Main function to extract citations and update articles."""
    print(f"Loading articles from {DATA_FILE}...")
    
    # Load articles
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    print(f"Loaded {len(articles)} articles")
    
    # Process each article
    total_citations = 0
    articles_with_citations = 0
    
    for i, article in enumerate(articles, 1):
        content = article.get('content', '')
        
        # Extract citations
        citations = extract_citation_urls(content)
        
        # Deduplicate citations
        unique_citations = deduplicate_citations(citations)
        
        # Add citations attribute
        article['citations'] = unique_citations
        
        if unique_citations:
            articles_with_citations += 1
            total_citations += len(unique_citations)
        
        if (i % 100 == 0) or (i == len(articles)):
            print(f"Processed {i}/{len(articles)} articles...")
    
    # Save updated articles
    print(f"\nSaving updated articles to {DATA_FILE}...")
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)
    
    print(f"Done!")
    print(f"  - Total articles: {len(articles)}")
    print(f"  - Articles with citations: {articles_with_citations}")
    print(f"  - Total unique citations: {total_citations}")


if __name__ == "__main__":
    main()

