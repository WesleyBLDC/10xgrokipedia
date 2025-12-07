# 10x-Grokipedia

## Inspiration

In the age of information overload, finding truth is harder than ever. Misinformation spreads faster than corrections, and even well-intentioned sources carry inherent biases. We built 10x-Grokipedia to empower power users and truth-seekers with the tools they need to evaluate, verify, and improve encyclopedia content at scale.

Our vision: accelerate the collaborative pursuit of truth by making bias visible, contradictions detectable, and sources transparent.

## What it does

10x-Grokipedia supercharges the encyclopedia experience with AI-powered analytics and verification tools:

- **Bias & Factuality Scoring**: Every article displays aggregate scores based on its citation sources. Hover over any footnote to instantly see that source's political bias (-10 to +10 scale) and factuality rating (0-10 scale).

- **Contradiction Detection**: Our system cross-references claims across articles and highlights text that contradicts information elsewhere. Click a highlighted claim to navigate directly to the conflicting article.

- **AI-Powered Edit Review**: When users suggest edits, Grok AI evaluates the proposed changes for accuracy, relevance, and source credibility before they're applied.

- **Citation Preview with AI Summary**: Hover over any citation to preview the source article without leaving the page. Each preview includes a Grok-generated summary for quick comprehension.

- **Version History with Per-Version Analytics**: Track how articles evolve over time. Each version recalculates bias scores based on that version's citations, allowing users to see how source quality changes.

- **Community Feed**: Real-time Twitter/X integration shows top tweets about each topic, ranked by engagement and summarized by Grok.

- **Interactive 3D Article Graph**: Explore article relationships in a full-screen 3D force-directed graph visualization. Nodes represent articles, sized by connection strength; edges are color-coded by relationship type (red for shared exact citations, yellow for direct internal links, cyan for shared citation domains). Hover over nodes to highlight connected articles, click to navigate, and drag to rotate the view. The graph dynamically centers on the current article and provides real-time stats about network connections.

- **Twitter Hover Search**: Select any text in an article to instantly search X/Twitter for related discussions. Grok AI optimizes your query by extracting key terms and building intelligent search queries. Results appear in the Community Feed sidebar with keyword highlighting, engagement metrics, and semantic ranking. Refine searches by adding or removing keywords, with real-time query optimization powered by Grok. Perfect for fact-checking claims or exploring public discourse on any topic.

- **Text Selection Tools**: Select any text in an article to access a context menu with options to search X/Twitter or suggest an edit. The selection toolbar appears automatically, making it effortless to verify claims or propose improvements.

## How we built it

**Architecture**: Monorepo with clear separation of concerns
- **Frontend**: React + TypeScript + Vite for a fast, responsive UI
- **Backend**: FastAPI (Python) for high-performance async API endpoints

**AI Integration**: Grok API powers multiple features
- Edit suggestion review and approval reasoning
- Tweet summarization (2-3 bullet points per topic)
- Article content summarization for citation previews
- Query optimization for Twitter/X searches from highlighted text (extracts keywords, suggests topics, builds OR queries)
- Semantic ranking of search results by relevance to selected text
- Real-time query refinement suggestions when searching X/Twitter

**Data Processing**:
- BeautifulSoup + html2text for article content extraction
- Pre-computed contradiction analysis using LLM-based claim comparison
- Citation bias database with domain-level factuality ratings
- Article graph generation analyzing citation patterns, internal links, and content similarity
- 3D graph visualization using react-force-graph-3d and Three.js with force-directed physics simulation
- Edge weighting system combining multiple relationship types (shared citations = 10.0, direct links = 8.0, shared domains = 5.0)

**Real-time Features**:
- In-memory caching with configurable TTLs
- Single-flight request deduplication to prevent redundant API calls
- Rate limiting with graceful degradation (serves cached data on 429)

## Challenges we ran into

- **Scaling contradiction detection**: Comparing claims across hundreds of articles required efficient text matching and offset tracking. We solved this with pre-computed LLM analysis and character-level offsets for precise highlighting.

- **Bias score aggregation**: Determining how to fairly aggregate scores from multiple citations with varying reliability required careful weighting and clear labeling.

- **Real-time Twitter integration**: Balancing API rate limits with fresh content required implementing smart caching, engagement-based ranking, and fallback strategies. Building the hover search feature required intelligent query construction from arbitrary text selections, keyword extraction, and semantic ranking to surface the most relevant tweets.

## Accomplishments that we're proud of

- Built a complete, functional platform in 24 hours with 8 major features
- Created an intuitive UI that surfaces complex analytics without overwhelming users
- Implemented end-to-end AI workflows: from suggestion submission to review to application
- Developed a citation preview system that makes source verification effortless
- Achieved seamless integration between bias scoring, version history, and contradiction detection
- Created an interactive 3D graph visualization that makes article relationships intuitive and explorable, with hover highlighting, click-to-navigate, and dynamic camera positioning
- Implemented context-aware text selection tools that bridge reading, research, and editing workflows
- Built a seamless Twitter hover search experience that transforms any text selection into an optimized X/Twitter query with AI-powered keyword extraction and semantic ranking

## What we learned

- How to employ LLM techniques to cross-reference articles and detect factual inconsistencies at scale
- Strategies for making bias and credibility metrics actionable and understandable
- The importance of caching and rate limiting when integrating multiple external APIs
- How to build AI-assisted editorial workflows that augment rather than replace human judgment

## What's next for 10x-Grokipedia

- **Automated article generation**: Use the same bias-checking and contradiction-detection techniques to generate new articles with built-in quality assurance
- **Expanded citation database**: Integrate more sources for broader bias/factuality coverage
- **User reputation system**: Track contributor accuracy over time to weight suggestions
- **Multi-language support**: Extend contradiction detection across language boundaries
- **Browser extension**: Bring Grokipedia's verification tools to any webpage
