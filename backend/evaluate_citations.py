#!/usr/bin/env python3
"""
Script to evaluate bias for citation links in articles.
Can process all articles or a specific article by title.
Generates a JSON file with one entry per citation link.

Usage:
    # Evaluate citations for all articles
    python3 evaluate_citations.py
    
    # Evaluate citations for a specific article
    python3 evaluate_citations.py --title "Billie Eilish"
    
    # List available articles (if title not found)
    python3 evaluate_citations.py --title "NonExistent"
"""

import json
import os
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Set, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import user, system
from bias import MBFCResponse, SYSTEM_PROMPT

# Load environment variables from .env file
load_dotenv()

# Paths
DATA_FILE = Path(__file__).parent / "all_articles_short.json"
OUTPUT_FILE = Path(__file__).parent / "citation_bias_evaluations.json"


def extract_citation_urls(content: str) -> Set[str]:
    """Extract all external citation URLs from markdown content."""
    urls = set()
    
    # Pattern to match markdown links: [](url) or [text](url)
    # We want external URLs (not internal /page/ links)
    link_pattern = r'\[([^\]]*)\]\(([^)]+)\)'
    
    for match in re.finditer(link_pattern, content):
        url = match.group(2)
        # Skip internal links
        if not url.startswith('/page/') and url.startswith('http'):
            urls.add(url)
    
    return urls


def load_articles() -> list[dict]:
    """Load all articles from the JSON file."""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def collect_all_citations(articles: list[dict]) -> dict[str, list[str]]:
    """
    Collect all unique citation URLs and track which articles reference them.
    Returns a dict mapping citation URL to list of article titles.
    """
    citation_to_articles = defaultdict(list)
    
    for article in articles:
        content = article.get('content', '')
        title = article.get('title', '')
        urls = extract_citation_urls(content)
        
        for url in urls:
            citation_to_articles[url].append(title)
    
    return dict(citation_to_articles)


def evaluate_citation_worker(args: Tuple[str, str]) -> Tuple[str, Optional[MBFCResponse]]:
    """
    Worker function to evaluate a single citation URL using Grok.
    Returns tuple of (citation_url, evaluation_result).
    """
    citation_url, api_key = args
    
    try:
        # Create client for this worker
        client = Client(api_key=api_key)
        
        # Create chat session
        chat = client.chat.create(model="grok-4-fast-reasoning")
        
        # Add system and user messages
        chat.append(system(SYSTEM_PROMPT))
        chat.append(user(f"Please evaluate this article URL: {citation_url}"))
        
        # Use parse method to get structured output directly as Pydantic model
        response, parsed_response = chat.parse(MBFCResponse)
        
        return (citation_url, parsed_response)
        
    except Exception as e:
        print(f"Error evaluating {citation_url}: {str(e)}")
        return (citation_url, None)


def main():
    """Main function to process all citations and generate evaluation file."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Evaluate citation bias for articles. Can process all articles or a specific one by title."
    )
    parser.add_argument(
        "--title",
        type=str,
        help="Process citations for a specific article title only"
    )
    args = parser.parse_args()
    
    # Check for API key
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        print("Error: XAI_API_KEY environment variable is not set")
        return
    
    # Get number of workers from environment or use default
    max_workers = int(os.getenv("EVALUATION_WORKERS", "5"))
    
    print("Loading articles...")
    articles = load_articles()
    print(f"Loaded {len(articles)} articles")
    
    # Filter articles if title specified
    if args.title:
        matching_articles = [a for a in articles if a.get('title') == args.title]
        if not matching_articles:
            print(f"Error: No article found with title '{args.title}'")
            print("\nAvailable articles:")
            for article in articles[:10]:
                print(f"  - {article.get('title')}")
            if len(articles) > 10:
                print(f"  ... and {len(articles) - 10} more")
            return
        articles_to_process = matching_articles
        print(f"Processing citations for article: '{args.title}'")
    else:
        articles_to_process = articles
        print("Processing citations for all articles")
    
    print("Extracting citation URLs...")
    citation_to_articles = collect_all_citations(articles_to_process)
    unique_citations = sorted(citation_to_articles.keys())
    print(f"Found {len(unique_citations)} unique citation URLs")
    
    if not unique_citations:
        print("No citations found!")
        return
    
    # Load existing results if file exists
    results = {}
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                results = json.load(f)
            print(f"Loaded {len(results)} existing evaluations")
        except Exception as e:
            print(f"Warning: Could not load existing results: {e}")
    
    # Filter out already evaluated citations
    remaining_citations = [url for url in unique_citations if url not in results]
    print(f"Remaining citations to evaluate: {len(remaining_citations)}")
    
    if not remaining_citations:
        print("All citations already evaluated!")
        return
    
    # Prepare arguments for workers (citation_url, api_key)
    worker_args = [(url, api_key) for url in remaining_citations]
    
    # Thread-safe lock for writing results
    results_lock = Lock()
    completed_count = [0]  # Use list to allow modification in nested function
    
    def update_progress(citation_url: str, evaluation: Optional[MBFCResponse]):
        """Update results and save progress."""
        with results_lock:
            if evaluation:
                results[citation_url] = {
                    "referenced_in_articles": citation_to_articles[citation_url],
                    "evaluation": evaluation.model_dump()
                }
                status = "✓ Success"
            else:
                status = "✗ Failed"
            
            completed_count[0] += 1
            total = len(remaining_citations)
            print(f"[{completed_count[0]}/{total}] {citation_url[:60]}... {status}")
            
            # Save progress periodically (every 10 evaluations)
            if completed_count[0] % 10 == 0:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                print(f"  Progress saved ({len(results)} total evaluations)")
    
    # Process citations in parallel
    print(f"\nStarting parallel evaluation with {max_workers} workers...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_url = {
            executor.submit(evaluate_citation_worker, args): args[0]
            for args in worker_args
        }
        
        # Process completed tasks as they finish
        for future in as_completed(future_to_url):
            citation_url, evaluation = future.result()
            update_progress(citation_url, evaluation)
    
    # Final save
    print(f"\nSaving final results to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Done! Evaluated {len(results)} citations out of {len(unique_citations)} total.")


if __name__ == "__main__":
    main()

