#!/usr/bin/env python3
"""
Generate article graph with edges based on multiple relationship signals.
Implements the edge definitions from graph_edge_definitions.md
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse
from typing import Dict, List, Set, Tuple
from itertools import combinations

# Paths
DATA_FILE = Path(__file__).parent / "all_articles_short.json"
OUTPUT_FILE = Path(__file__).parent / "article_graph.json"

# Edge weights (from graph_edge_definitions.md)
WEIGHTS = {
    "shared_exact_citations": 10.0,
    "shared_domains": 5.0,
    "domain_jaccard": 3.0,
    "direct_link": 8.0,
    "bidirectional_link": 4.0,  # Additional weight for bidirectional
    "co_linked": 2.0,
    "title_similarity": 1.0,
    "keyword_overlap": 1.5,
}

MIN_EDGE_WEIGHT = 1.0
MAX_EDGES_PER_NODE = 15


def get_root_domain(url: str) -> str:
    """Extract root domain from URL."""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except:
        return url


def extract_internal_links(content: str) -> Set[str]:
    """Extract all internal page links from markdown content."""
    links = set()
    link_pattern = r'\[([^\]]*)\]\(([^)]+)\)'
    
    for match in re.finditer(link_pattern, content):
        url = match.group(2)
        if url.startswith('/page/'):
            article_name = url.replace('/page/', '')
            links.add(article_name)
    
    return links


def calculate_title_similarity(title1: str, title2: str) -> float:
    """Calculate simple title similarity score."""
    # Check for series patterns (e.g., "Series 1", "Series 2")
    if title1 == title2:
        return 1.0
    
    # Check if one title contains the other (for series)
    if title1 in title2 or title2 in title1:
        return 0.5
    
    # Simple prefix matching
    words1 = set(title1.lower().split())
    words2 = set(title2.lower().split())
    if not words1 or not words2:
        return 0.0
    
    intersection = words1 & words2
    union = words1 | words2
    if not union:
        return 0.0
    
    return len(intersection) / len(union)


def extract_slug(url: str) -> str:
    """Extract article slug from URL."""
    if '/page/' in url:
        return url.split('/page/')[-1]
    return url


def generate_graph() -> Dict:
    """Generate article graph with edges."""
    print(f"Loading articles from {DATA_FILE}...")
    
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    print(f"Loaded {len(articles)} articles")
    
    # Build article index by slug (from URL) and by title (for internal link resolution)
    articles_by_slug = {}
    articles_by_title = {}
    for article in articles:
        url = article.get('url', '')
        if not url:
            print(f"Warning: Article '{article.get('title', 'Unknown')}' has no URL, skipping")
            continue
        slug = extract_slug(url)
        articles_by_slug[slug] = article
        articles_by_title[article.get('title', '')] = article
    
    article_slugs = list(articles_by_slug.keys())
    print(f"Processing {len(article_slugs)} articles")
    
    # Precompute article data
    article_data = {}
    for slug, article in articles_by_slug.items():
        content = article.get('content', '')
        citations = article.get('citations', [])
        title = article.get('title', '')
        
        # Extract citation domains
        citation_domains = {get_root_domain(c) for c in citations if c.startswith('http')}
        
        # Extract internal links (these are slugs from /page/ links)
        internal_link_slugs = extract_internal_links(content)
        # Resolve internal links to slugs (they're already slugs from the URL)
        internal_link_ids = set()
        for link_slug in internal_link_slugs:
            # Try to find article by slug (from the link)
            if link_slug in articles_by_slug:
                internal_link_ids.add(link_slug)
            else:
                # Fallback: try to find by title
                linked_article = articles_by_title.get(link_slug)
                if linked_article:
                    linked_slug = extract_slug(linked_article.get('url', ''))
                    if linked_slug:
                        internal_link_ids.add(linked_slug)
        
        article_data[slug] = {
            'citations': set(citations),
            'citation_domains': citation_domains,
            'internal_links': internal_link_ids,
            'title': title,
        }
    
    # Build edges
    edges = []
    edge_weights = defaultdict(float)
    edge_types = defaultdict(set)
    edge_metadata = defaultdict(dict)
    
    print("Calculating edges...")
    
    # 1. Citation-based edges
    print("  - Processing citation-based edges...")
    
    # Shared exact citations
    for slug1, slug2 in combinations(article_slugs, 2):
        data1 = article_data[slug1]
        data2 = article_data[slug2]
        
        shared_citations = data1['citations'] & data2['citations']
        if shared_citations:
            weight = WEIGHTS['shared_exact_citations'] * (len(shared_citations) / 5.0)  # Normalize
            edge_weights[(slug1, slug2)] += weight
            edge_types[(slug1, slug2)].add('shared_exact_citations')
            if 'shared_citations' not in edge_metadata[(slug1, slug2)]:
                edge_metadata[(slug1, slug2)]['shared_citations'] = []
            edge_metadata[(slug1, slug2)]['shared_citations'].extend(list(shared_citations))
    
    # Shared citation domains
    max_shared_domains = 0
    domain_sharing = defaultdict(int)
    
    for slug1, slug2 in combinations(article_slugs, 2):
        data1 = article_data[slug1]
        data2 = article_data[slug2]
        
        shared_domains = data1['citation_domains'] & data2['citation_domains']
        if shared_domains:
            count = len(shared_domains)
            domain_sharing[(slug1, slug2)] = count
            max_shared_domains = max(max_shared_domains, count)
    
    # Normalize and add weights
    for (slug1, slug2), count in domain_sharing.items():
        if max_shared_domains > 0:
            weight = WEIGHTS['shared_domains'] * (count / max_shared_domains)
            edge_weights[(slug1, slug2)] += weight
            edge_types[(slug1, slug2)].add('shared_domains')
            if 'shared_domains' not in edge_metadata[(slug1, slug2)]:
                edge_metadata[(slug1, slug2)]['shared_domains'] = []
            data1 = article_data[slug1]
            data2 = article_data[slug2]
            shared_domains = data1['citation_domains'] & data2['citation_domains']
            edge_metadata[(slug1, slug2)]['shared_domains'] = list(shared_domains)
    
    # Domain Jaccard similarity
    for slug1, slug2 in combinations(article_slugs, 2):
        data1 = article_data[slug1]
        data2 = article_data[slug2]
        
        domains1 = data1['citation_domains']
        domains2 = data2['citation_domains']
        
        if domains1 or domains2:
            intersection = len(domains1 & domains2)
            union = len(domains1 | domains2)
            if union > 0:
                jaccard = intersection / union
                if jaccard > 0:
                    weight = WEIGHTS['domain_jaccard'] * jaccard
                    edge_weights[(slug1, slug2)] += weight
                    edge_types[(slug1, slug2)].add('domain_jaccard')
    
    # 2. Internal link edges
    print("  - Processing internal link edges...")
    
    # Direct links
    for slug1, data1 in article_data.items():
        for linked_slug in data1['internal_links']:
            if linked_slug in articles_by_slug:
                # A -> B
                edge_key = (slug1, linked_slug)
                edge_weights[edge_key] += WEIGHTS['direct_link']
                edge_types[edge_key].add('direct_link')
                if 'link_direction' not in edge_metadata[edge_key]:
                    edge_metadata[edge_key]['link_direction'] = []
                edge_metadata[edge_key]['link_direction'].append(f"{slug1}->{linked_slug}")
                
                # Check if bidirectional
                data2 = article_data.get(linked_slug, {})
                if slug1 in data2.get('internal_links', set()):
                    edge_weights[edge_key] += WEIGHTS['bidirectional_link']
                    edge_types[edge_key].add('bidirectional_link')
                    edge_metadata[edge_key]['link_direction'].append(f"{linked_slug}->{slug1}")
    
    # Co-linked articles
    link_targets = defaultdict(set)
    for article_slug, data in article_data.items():
        for target_slug in data['internal_links']:
            if target_slug in articles_by_slug:
                link_targets[target_slug].add(article_slug)
    
    for target_slug, sources in link_targets.items():
        if len(sources) > 1:
            for source1, source2 in combinations(sources, 2):
                edge_key = (source1, source2)
                weight = WEIGHTS['co_linked'] * (len(link_targets[target_slug]) ** 0.5)
                edge_weights[edge_key] += weight
                edge_types[edge_key].add('co_linked')
                if 'co_linked_targets' not in edge_metadata[edge_key]:
                    edge_metadata[edge_key]['co_linked_targets'] = []
                edge_metadata[edge_key]['co_linked_targets'].append(target_slug)
    
    # 3. Content-based edges
    print("  - Processing content-based edges...")
    
    # Title similarity
    for slug1, slug2 in combinations(article_slugs, 2):
        title1 = article_data[slug1]['title']
        title2 = article_data[slug2]['title']
        similarity = calculate_title_similarity(title1, title2)
        if similarity > 0.1:  # Threshold
            weight = WEIGHTS['title_similarity'] * similarity
            edge_weights[(slug1, slug2)] += weight
            edge_types[(slug1, slug2)].add('title_similarity')
    
    # Build final edges list
    print("  - Building final edges...")
    
    for (source, target), weight in edge_weights.items():
        if weight >= MIN_EDGE_WEIGHT:
            edges.append({
                'source': source,
                'target': target,
                'weight': round(weight, 2),
                'types': list(edge_types[(source, target)]),
                'metadata': edge_metadata.get((source, target), {})
            })
    
    # Limit edges per node
    edges_by_source = defaultdict(list)
    for edge in edges:
        edges_by_source[edge['source']].append(edge)
    
    filtered_edges = []
    for source, source_edges in edges_by_source.items():
        sorted_edges = sorted(source_edges, key=lambda x: x['weight'], reverse=True)
        filtered_edges.extend(sorted_edges[:MAX_EDGES_PER_NODE])
    
    # Build nodes
    nodes = []
    for slug, article in articles_by_slug.items():
        data = article_data[slug]
        nodes.append({
            'id': slug,  # Use slug as node ID
            'title': data['title'],
            'citation_count': len(data['citations']),
            'outgoing_links': len(data['internal_links']),
            'citation_domains_count': len(data['citation_domains'])
        })
    
    graph = {
        'nodes': nodes,
        'edges': filtered_edges,
        'stats': {
            'total_nodes': len(nodes),
            'total_edges': len(filtered_edges),
            'edges_by_type': {
                edge_type: sum(1 for e in filtered_edges if edge_type in e['types'])
                for edge_type in ['shared_exact_citations', 'shared_domains', 'domain_jaccard',
                                 'direct_link', 'bidirectional_link', 'co_linked', 'title_similarity']
            }
        }
    }
    
    return graph


def main():
    """Main function."""
    graph = generate_graph()
    
    print(f"\n{'='*80}")
    print(f"GRAPH GENERATION COMPLETE")
    print(f"{'='*80}")
    print(f"\nNodes: {graph['stats']['total_nodes']}")
    print(f"Edges: {graph['stats']['total_edges']}")
    print(f"\nEdges by type:")
    for edge_type, count in graph['stats']['edges_by_type'].items():
        print(f"  {edge_type}: {count}")
    
    # Save graph
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    
    print(f"\nGraph saved to: {OUTPUT_FILE}")
    
    # Show sample edges
    print(f"\n{'='*80}")
    print(f"SAMPLE EDGES (Top 10 by weight)")
    print(f"{'='*80}\n")
    
    # Build a lookup for node titles
    node_title_map = {node['id']: node['title'] for node in graph['nodes']}
    
    sorted_edges = sorted(graph['edges'], key=lambda x: x['weight'], reverse=True)
    for i, edge in enumerate(sorted_edges[:10], 1):
        source_title = node_title_map.get(edge['source'], edge['source'])
        target_title = node_title_map.get(edge['target'], edge['target'])
        print(f"{i}. {source_title} -> {target_title}")
        print(f"   Weight: {edge['weight']}, Types: {', '.join(edge['types'])}")
        print()


if __name__ == "__main__":
    main()

