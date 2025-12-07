# Article Graph Edge Definitions

## Overview
This document defines how edges should be created between articles in the graph view, based on different relationship signals.

## Edge Types

### 1. **Citation-Based Edges** (Strongest Signal)

#### 1a. Shared Exact Citations (Weight: 10.0)
- **Definition**: Two articles share the exact same citation URL
- **Rationale**: Very strong signal - if two articles cite the same source, they likely discuss related topics
- **Current stats**: 51 shared exact citations across 70 articles
- **Edge weight formula**: `weight = 10.0 * (shared_citations_count / max_shared_citations)`
  - Normalize by the maximum number of shared citations in the dataset

#### 1b. Shared Citation Domains (Weight: 5.0)
- **Definition**: Two articles cite URLs from the same domain (e.g., both cite youtube.com)
- **Rationale**: Strong signal - shared sources indicate topical similarity
- **Current stats**: 510 shared domains, 68 articles participate
- **Edge weight formula**: `weight = 5.0 * (shared_domains_count / max_shared_domains)`
  - Count how many unique domains are shared between two articles
  - Normalize by maximum shared domains

#### 1c. Citation Domain Overlap Score (Weight: 3.0)
- **Definition**: Jaccard similarity of citation domains between two articles
- **Rationale**: Accounts for both shared and unique domains
- **Formula**: `jaccard = intersection(domains_A, domains_B) / union(domains_A, domains_B)`
- **Edge weight**: `weight = 3.0 * jaccard`

### 2. **Internal Link Edges** (Direct Relationships)

#### 2a. Direct Links (Weight: 8.0)
- **Definition**: Article A contains a link to Article B (`/page/ArticleB`)
- **Rationale**: Explicit relationship - one article references another
- **Current stats**: 6,891 internal links, but most point to non-existing articles
- **Edge weight**: 
  - `weight = 8.0` if Article A links to Article B
  - `weight = 4.0` if bidirectional (both link to each other)

#### 2b. Co-linked Articles (Weight: 2.0)
- **Definition**: Two articles both link to the same third article
- **Rationale**: Articles that reference the same topics are related
- **Edge weight**: `weight = 2.0 * sqrt(shared_targets_count)`
  - Square root to prevent over-weighting

### 3. **Content-Based Edges** (Semantic Similarity)

#### 3a. Title Similarity (Weight: 1.0)
- **Definition**: Articles with similar titles (e.g., series episodes)
- **Rationale**: Series or related topics often have similar naming
- **Detection**: String similarity (Levenshtein, prefix matching)
- **Edge weight**: `weight = 1.0 * similarity_score`

#### 3b. Shared Keywords (Weight: 1.5)
- **Definition**: Articles that share significant keywords in their content
- **Rationale**: Similar topics use similar terminology
- **Implementation**: Extract keywords, compute TF-IDF, find overlaps
- **Edge weight**: `weight = 1.5 * keyword_overlap_score`

## Recommended Edge Weight Calculation

### Combined Weight Formula
For each pair of articles (A, B), compute:

```
total_weight = 
  (shared_exact_citations_weight) +
  (shared_domains_weight) +
  (domain_jaccard_weight) +
  (direct_link_weight) +
  (co_linked_weight) +
  (title_similarity_weight) +
  (keyword_overlap_weight)
```

### Edge Filtering
- **Minimum threshold**: Only create edges with `total_weight >= 1.0`
- **Maximum edges per node**: Limit to top 10-15 edges per article to avoid clutter
- **Bidirectional**: Create edges in both directions, but weight may differ

## Graph Structure

### Node Properties
- `id`: Article slug/title
- `title`: Display title
- `type`: Article type (if applicable)
- `citation_count`: Number of citations
- `outgoing_links`: Number of internal links

### Edge Properties
- `source`: Source article ID
- `target`: Target article ID
- `weight`: Combined weight (0-20+ range)
- `types`: Array of edge types contributing to this edge
  - e.g., `["shared_domains", "direct_link"]`
- `metadata`: Additional info
  - `shared_citations`: List of shared citation URLs
  - `shared_domains`: List of shared domains
  - `link_direction`: "A->B", "B->A", or "bidirectional"

## Implementation Priority

### Phase 1 (MVP)
1. Shared citation domains (1b) - Strong signal, already analyzed
2. Direct links (2a) - Explicit relationships
3. Shared exact citations (1a) - Strong but sparse

### Phase 2 (Enhanced)
4. Citation domain overlap (1c) - Better similarity measure
5. Co-linked articles (2b) - Broader connections

### Phase 3 (Advanced)
6. Content-based edges (3a, 3b) - Requires NLP/ML

## Example Edge Calculation

**Articles**: "Billie Eilish" and "Finneas O'Connell"

**Signals**:
- Shared exact citations: 3 URLs → weight = 10.0 * (3/5) = 6.0
- Shared domains: 8 domains → weight = 5.0 * (8/15) = 2.67
- Domain Jaccard: 0.4 → weight = 3.0 * 0.4 = 1.2
- Direct link: "Billie Eilish" links to "Finneas O'Connell" → weight = 8.0
- Title similarity: 0.1 → weight = 1.0 * 0.1 = 0.1

**Total weight**: 6.0 + 2.67 + 1.2 + 8.0 + 0.1 = **18.0**

This would be a very strong edge, indicating these articles are highly related.

