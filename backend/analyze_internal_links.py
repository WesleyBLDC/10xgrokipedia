#!/usr/bin/env python3
"""
Script to analyze internal links between articles.
Finds how many articles link to other articles and which articles are most linked-to.
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set

# Paths
DATA_FILE = Path(__file__).parent / "all_articles_short.json"


def extract_internal_links(content: str) -> Set[str]:
    """Extract all internal page links from markdown content."""
    links = set()
    
    # Pattern to match markdown links: [text](/page/ArticleName)
    link_pattern = r'\[([^\]]*)\]\(([^)]+)\)'
    
    for match in re.finditer(link_pattern, content):
        url = match.group(2)
        # Only include internal /page/ links
        if url.startswith('/page/'):
            # Extract the article name from /page/ArticleName
            article_name = url.replace('/page/', '')
            links.add(article_name)
    
    return links


def analyze_internal_links():
    """Analyze internal links between articles."""
    print(f"Loading articles from {DATA_FILE}...")
    
    # Load articles
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    print(f"Loaded {len(articles)} articles")
    
    # Create a mapping from article title to article data
    articles_by_title = {article.get('title', ''): article for article in articles}
    
    # Track which articles link to which other articles
    # link_target -> list of source article titles
    links_to_article = defaultdict(list)
    
    # Track which articles have outgoing links
    articles_with_links = set()
    
    # Track total link count
    total_links = 0
    
    for article in articles:
        title = article.get('title', '')
        content = article.get('content', '')
        
        # Extract internal links
        internal_links = extract_internal_links(content)
        
        if internal_links:
            articles_with_links.add(title)
            total_links += len(internal_links)
            
            # Track which articles this article links to
            for linked_article in internal_links:
                links_to_article[linked_article].append(title)
    
    return articles_by_title, links_to_article, articles_with_links, total_links


def main():
    """Main function to analyze and display internal links."""
    articles_by_title, links_to_article, articles_with_links, total_links = analyze_internal_links()
    
    # Separate links to existing articles vs non-existing articles
    valid_links = {
        target: sources 
        for target, sources in links_to_article.items() 
        if target in articles_by_title
    }
    
    invalid_links = {
        target: sources 
        for target, sources in links_to_article.items() 
        if target not in articles_by_title
    }
    
    # Sort by number of incoming links (descending)
    sorted_valid_links = sorted(
        valid_links.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )
    
    sorted_all_links = sorted(
        links_to_article.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )
    
    print(f"\n{'='*80}")
    print(f"INTERNAL LINKS ANALYSIS")
    print(f"{'='*80}")
    print(f"\nTotal articles: {len(articles_by_title)}")
    print(f"Articles with outgoing links: {len(articles_with_links)}")
    print(f"Total internal links: {total_links}")
    print(f"Unique article targets linked to: {len(links_to_article)}")
    print(f"  - Links to existing articles: {len(valid_links)}")
    print(f"  - Links to non-existing articles: {len(invalid_links)}")
    
    print(f"\n{'='*80}")
    print(f"TOP 20 MOST LINKED-TO ARTICLES (ALL LINKS)")
    print(f"{'='*80}\n")
    
    for i, (target_article, source_articles) in enumerate(sorted_all_links[:20], 1):
        exists = "✓" if target_article in articles_by_title else "✗"
        print(f"{i}. [{exists}] Article: {target_article}")
        print(f"   Linked from {len(source_articles)} article(s):")
        for source in source_articles[:5]:  # Show first 5 sources
            print(f"      - {source}")
        if len(source_articles) > 5:
            print(f"      ... and {len(source_articles) - 5} more")
        print()
    
    if valid_links:
        print(f"\n{'='*80}")
        print(f"TOP 20 MOST LINKED-TO ARTICLES (EXISTING ARTICLES ONLY)")
        print(f"{'='*80}\n")
        
        for i, (target_article, source_articles) in enumerate(sorted_valid_links[:20], 1):
            print(f"{i}. Article: {target_article}")
            print(f"   Linked from {len(source_articles)} article(s):")
            for source in source_articles[:10]:  # Show first 10 sources
                print(f"      - {source}")
            if len(source_articles) > 10:
                print(f"      ... and {len(source_articles) - 10} more")
            print()
    
    # Summary statistics
    print(f"\n{'='*80}")
    print(f"SUMMARY STATISTICS")
    print(f"{'='*80}\n")
    
    all_link_counts = [len(sources) for sources in links_to_article.values()]
    valid_link_counts = [len(sources) for sources in valid_links.values()]
    
    print(f"All links (including to non-existing articles):")
    print(f"  Articles linked to by 1 article: {sum(1 for c in all_link_counts if c == 1)}")
    print(f"  Articles linked to by 2-5 articles: {sum(1 for c in all_link_counts if 2 <= c <= 5)}")
    print(f"  Articles linked to by 6-10 articles: {sum(1 for c in all_link_counts if 6 <= c <= 10)}")
    print(f"  Articles linked to by 11-20 articles: {sum(1 for c in all_link_counts if 11 <= c <= 20)}")
    print(f"  Articles linked to by 21+ articles: {sum(1 for c in all_link_counts if c >= 21)}")
    print(f"  Maximum incoming links: {max(all_link_counts) if all_link_counts else 0}")
    
    if valid_link_counts:
        print(f"\nLinks to existing articles only:")
        print(f"  Articles linked to by 1 article: {sum(1 for c in valid_link_counts if c == 1)}")
        print(f"  Articles linked to by 2-5 articles: {sum(1 for c in valid_link_counts if 2 <= c <= 5)}")
        print(f"  Articles linked to by 6-10 articles: {sum(1 for c in valid_link_counts if 6 <= c <= 10)}")
        print(f"  Articles linked to by 11-20 articles: {sum(1 for c in valid_link_counts if 11 <= c <= 20)}")
        print(f"  Articles linked to by 21+ articles: {sum(1 for c in valid_link_counts if c >= 21)}")
        print(f"  Maximum incoming links: {max(valid_link_counts)}")
    
    # Save detailed results to JSON
    output_file = Path(__file__).parent / "internal_links_analysis.json"
    output_data = {
        "total_articles": len(articles_by_title),
        "articles_with_outgoing_links": len(articles_with_links),
        "total_internal_links": total_links,
        "unique_article_targets": len(links_to_article),
        "links_to_existing_articles": len(valid_links),
        "links_to_non_existing_articles": len(invalid_links),
        "most_linked_articles_all": [
            {
                "article": target,
                "exists": target in articles_by_title,
                "incoming_link_count": len(sources),
                "linked_from": sources
            }
            for target, sources in sorted_all_links[:50]
        ],
        "most_linked_articles_existing": [
            {
                "article": target,
                "incoming_link_count": len(sources),
                "linked_from": sources
            }
            for target, sources in sorted_valid_links
        ]
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()

