#!/usr/bin/env python3
"""
Script to find citations that are shared across multiple articles,
considering only the root domain/base URL level.
"""

import json
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse
from typing import Dict, List

# Paths
DATA_FILE = Path(__file__).parent / "all_articles_short.json"


def get_root_domain(url: str) -> str:
    """Extract root domain from URL (scheme + netloc)."""
    try:
        parsed = urlparse(url)
        # Return scheme + netloc (e.g., https://www.example.com)
        return f"{parsed.scheme}://{parsed.netloc}"
    except:
        return url


def find_shared_citations_by_domain() -> Dict[str, List[str]]:
    """
    Find all citation domains that appear in multiple articles.
    Returns a dict mapping root domain to list of article titles.
    """
    print(f"Loading articles from {DATA_FILE}...")
    
    # Load articles
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    print(f"Loaded {len(articles)} articles")
    
    # Build mapping: root domain -> list of article titles
    domain_to_articles = defaultdict(list)
    
    # Also track full URLs for reference
    domain_to_full_urls = defaultdict(set)
    
    for article in articles:
        title = article.get('title', 'Unknown')
        citations = article.get('citations', [])
        
        for citation in citations:
            root_domain = get_root_domain(citation)
            domain_to_articles[root_domain].append(title)
            domain_to_full_urls[root_domain].add(citation)
    
    # Filter to only domains that appear in 2+ articles
    shared_domains = {
        domain: articles 
        for domain, articles in domain_to_articles.items() 
        if len(articles) > 1
    }
    
    return shared_domains, domain_to_full_urls


def main():
    """Main function to find and display shared citation domains."""
    shared_domains, domain_to_full_urls = find_shared_citations_by_domain()
    
    # Sort by number of articles (descending)
    sorted_domains = sorted(
        shared_domains.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )
    
    print(f"\n{'='*80}")
    print(f"SHARED CITATION DOMAINS ANALYSIS")
    print(f"{'='*80}")
    print(f"\nTotal articles analyzed: {len(json.load(open(DATA_FILE, 'r', encoding='utf-8')))}")
    print(f"Total unique citation domains shared by 2+ articles: {len(shared_domains)}")
    
    if not shared_domains:
        print("\nNo citation domains are shared across multiple articles.")
        return
    
    print(f"\n{'='*80}")
    print(f"TOP 30 MOST SHARED CITATION DOMAINS")
    print(f"{'='*80}\n")
    
    for i, (domain, articles) in enumerate(sorted_domains[:30], 1):
        unique_articles = list(set(articles))  # Remove duplicates
        print(f"{i}. Domain: {domain}")
        print(f"   Shared by {len(unique_articles)} unique article(s) ({len(articles)} total references)")
        print(f"   Sample URLs from this domain: {len(domain_to_full_urls[domain])} unique URLs")
        for article in unique_articles[:10]:  # Show first 10 articles
            print(f"      - {article}")
        if len(unique_articles) > 10:
            print(f"      ... and {len(unique_articles) - 10} more")
        print()
    
    # Summary statistics
    print(f"\n{'='*80}")
    print(f"SUMMARY STATISTICS")
    print(f"{'='*80}\n")
    
    article_counts = [len(set(articles)) for articles in shared_domains.values()]
    
    print(f"Domains shared by 2 articles: {sum(1 for c in article_counts if c == 2)}")
    print(f"Domains shared by 3-5 articles: {sum(1 for c in article_counts if 3 <= c <= 5)}")
    print(f"Domains shared by 6-10 articles: {sum(1 for c in article_counts if 6 <= c <= 10)}")
    print(f"Domains shared by 11-20 articles: {sum(1 for c in article_counts if 11 <= c <= 20)}")
    print(f"Domains shared by 21+ articles: {sum(1 for c in article_counts if c >= 21)}")
    print(f"\nMaximum number of articles sharing a single domain: {max(article_counts) if article_counts else 0}")
    
    # Calculate total unique articles that share at least one domain
    all_articles_with_shared_domains = set()
    for articles in shared_domains.values():
        all_articles_with_shared_domains.update(articles)
    
    print(f"\nTotal unique articles that share at least one citation domain: {len(all_articles_with_shared_domains)}")
    
    # Save detailed results to JSON
    output_file = Path(__file__).parent / "shared_citations_by_domain.json"
    output_data = {
        "total_shared_domains": len(shared_domains),
        "total_articles_sharing_domains": len(all_articles_with_shared_domains),
        "domains": {
            domain: {
                "domain": domain,
                "unique_article_count": len(set(articles)),
                "total_references": len(articles),
                "unique_url_count": len(domain_to_full_urls[domain]),
                "articles": list(set(articles))
            }
            for domain, articles in sorted_domains
        }
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()

