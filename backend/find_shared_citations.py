#!/usr/bin/env python3
"""
Script to find citations that are shared across multiple articles.
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

# Paths
DATA_FILE = Path(__file__).parent / "all_articles_short.json"


def find_shared_citations() -> Dict[str, List[str]]:
    """
    Find all citations that appear in multiple articles.
    Returns a dict mapping citation URL to list of article titles.
    """
    print(f"Loading articles from {DATA_FILE}...")
    
    # Load articles
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    print(f"Loaded {len(articles)} articles")
    
    # Build mapping: citation URL -> list of article titles
    citation_to_articles = defaultdict(list)
    
    for article in articles:
        title = article.get('title', 'Unknown')
        citations = article.get('citations', [])
        
        for citation in citations:
            citation_to_articles[citation].append(title)
    
    # Filter to only citations that appear in 2+ articles
    shared_citations = {
        citation: articles 
        for citation, articles in citation_to_articles.items() 
        if len(articles) > 1
    }
    
    return shared_citations


def main():
    """Main function to find and display shared citations."""
    shared_citations = find_shared_citations()
    
    # Sort by number of articles (descending)
    sorted_citations = sorted(
        shared_citations.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )
    
    print(f"\n{'='*80}")
    print(f"SHARED CITATIONS ANALYSIS")
    print(f"{'='*80}")
    print(f"\nTotal articles analyzed: {len(json.load(open(DATA_FILE, 'r', encoding='utf-8')))}")
    print(f"Total unique citations shared by 2+ articles: {len(shared_citations)}")
    
    if not shared_citations:
        print("\nNo citations are shared across multiple articles.")
        return
    
    print(f"\n{'='*80}")
    print(f"TOP 20 MOST SHARED CITATIONS")
    print(f"{'='*80}\n")
    
    for i, (citation, articles) in enumerate(sorted_citations[:20], 1):
        print(f"{i}. Citation URL: {citation}")
        print(f"   Shared by {len(articles)} article(s):")
        for article in articles:
            print(f"      - {article}")
        print()
    
    # Summary statistics
    print(f"\n{'='*80}")
    print(f"SUMMARY STATISTICS")
    print(f"{'='*80}\n")
    
    citation_counts = [len(articles) for articles in shared_citations.values()]
    
    print(f"Citations shared by 2 articles: {sum(1 for c in citation_counts if c == 2)}")
    print(f"Citations shared by 3 articles: {sum(1 for c in citation_counts if c == 3)}")
    print(f"Citations shared by 4 articles: {sum(1 for c in citation_counts if c == 4)}")
    print(f"Citations shared by 5+ articles: {sum(1 for c in citation_counts if c >= 5)}")
    print(f"\nMaximum number of articles sharing a single citation: {max(citation_counts) if citation_counts else 0}")
    
    # Save detailed results to JSON
    output_file = Path(__file__).parent / "shared_citations.json"
    output_data = {
        "total_shared_citations": len(shared_citations),
        "citations": {
            citation: {
                "url": citation,
                "article_count": len(articles),
                "articles": articles
            }
            for citation, articles in sorted_citations
        }
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()

