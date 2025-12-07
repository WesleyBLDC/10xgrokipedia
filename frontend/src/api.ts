const API_BASE = "http://localhost:8000/api";

export interface TopicSummary {
  topic: string;
  title: string;
}

export interface Topic {
  topic: string;
  title: string;
  content: string;
  suggestion_count: number;
  id?: string | null;
}

export interface ReviewResult {
  approved: boolean;
  reasoning: string;
  suggested_content: string | null;
}

export interface Suggestion {
  id: string;
  highlighted_text: string;
  summary: string;
  sources: string[];
  status: "pending" | "reviewed" | "applied" | "rejected";
  review_result: ReviewResult | null;
  created_at: string;
}

export interface EditSuggestionInput {
  highlighted_text: string;
  summary: string;
  sources: string[];
}

export interface VersionSummary {
  index: number;
  timestamp: string;
}

export interface VersionDetail {
  index: number;
  timestamp: string;
  content: string;
}

export interface TweetItem {
  id: string;
  text: string;
  author_username: string;
  author_name?: string | null;
  author_profile_image_url?: string | null;
  author_verified?: boolean | null;
  author_verified_type?: string | null;
  created_at?: string | null;
  like_count?: number | null;
  retweet_count?: number | null;
  reply_count?: number | null;
  quote_count?: number | null;
  url: string;
  trending?: boolean | null;
}

export interface TweetsSummary {
  bullets: string[];
  model?: string | null;
  cached: boolean;
}

// Search hints from Grok query optimization
export interface SearchHints {
  query: string;
  keywords: string[];
  topics: string[];
}

export interface SearchResult {
  tweets: TweetItem[];
  hints?: SearchHints | null;
}

export interface AggregateBias {
  article_title: string;
  article_url: string;
  citation_count: number;
  evaluated_citation_count: number;
  average_factual_score: number;
  factual_label: string;
  average_bias_score: number;
  bias_label: string;
}

export interface CitationBias {
  citation_url: string;
  factual_score: number;
  factual_label: string;
  bias_score: number;
  bias_label: string;
}

export async function searchTopics(query: string): Promise<TopicSummary[]> {
  const res = await fetch(`${API_BASE}/topics/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("Failed to search topics");
  return res.json();
}

export async function getTopic(slug: string): Promise<Topic> {
  const res = await fetch(`${API_BASE}/topics/${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error("Topic not found");
  return res.json();
}

export async function getTopicTweets(slug: string, maxResults = 10): Promise<TweetItem[]> {
  const res = await fetch(
    `${API_BASE}/topics/${encodeURIComponent(slug)}/tweets?max_results=${maxResults}`
  );
  if (!res.ok) {
    // Surface error text for better UX
    const msg = await res.text();
    throw new Error(msg || "Failed to load tweets");
  }
  return res.json();
}

export async function searchTweets(
  query: string,
  maxResults = 10,
  opts?: { optimize?: boolean; nocache?: boolean }
): Promise<SearchResult> {
  const optimize = opts?.optimize !== undefined ? (opts.optimize ? 1 : 0) : 1;
  const nocache = opts?.nocache ? 1 : 0;
  const res = await fetch(
    `${API_BASE}/tweets/search?q=${encodeURIComponent(query)}&max_results=${maxResults}&optimize=${optimize}&nocache=${nocache}`
  );
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || "Failed to load tweets");
  }
  return res.json();
}

export async function getTopicTweetsSummary(slug: string, maxResults = 10): Promise<TweetsSummary> {
  const res = await fetch(
    `${API_BASE}/topics/${encodeURIComponent(slug)}/tweets/summary?max_results=${maxResults}`
  );
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || "Failed to load summary");
  }
  return res.json();
}

export async function refreshTopicTweets(slug: string): Promise<void> {
  const res = await fetch(`${API_BASE}/topics/${encodeURIComponent(slug)}/tweets/refresh`, {
    method: "POST",
  });
  if (!res.ok && res.status !== 204) {
    const msg = await res.text();
    throw new Error(msg || "Failed to refresh tweets cache");
  }
}

export async function submitSuggestion(slug: string, suggestion: EditSuggestionInput): Promise<Suggestion> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(slug)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(suggestion),
  });
  if (!res.ok) throw new Error("Failed to submit suggestion");
  return res.json();
}

export async function getSuggestions(slug: string): Promise<Suggestion[]> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error("Failed to get suggestions");
  return res.json();
}

export async function reviewSuggestion(slug: string, suggestionId: string): Promise<ReviewResult> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(slug)}/review/${suggestionId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to review suggestion");
  return res.json();
}

export async function applySuggestion(slug: string, suggestionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(slug)}/apply/${suggestionId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to apply suggestion");
}

export async function rejectSuggestion(slug: string, suggestionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(slug)}/reject/${suggestionId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to reject suggestion");
}

export async function getVersions(slug: string): Promise<VersionSummary[]> {
  const res = await fetch(`${API_BASE}/topics/${encodeURIComponent(slug)}/versions`);
  if (!res.ok) throw new Error("Failed to get versions");
  return res.json();
}

export async function getVersion(slug: string, index: number): Promise<VersionDetail> {
  const res = await fetch(`${API_BASE}/topics/${encodeURIComponent(slug)}/versions/${index}`);
  if (!res.ok) throw new Error("Failed to get version");
  return res.json();
}

export async function getAggregateBias(slug: string, versionIndex?: number): Promise<AggregateBias | null> {
  try {
    let url = `${API_BASE}/aggregate_bias/${encodeURIComponent(slug)}`;
    if (versionIndex !== undefined) {
      url += `?version_index=${versionIndex}`;
    }
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export interface CitationBias {
  citation_url: string;
  factual_score: number;
  factual_label: string;
  bias_score: number;
  bias_label: string;
}

export async function getCitationBias(url: string): Promise<CitationBias | null> {
  try {
    const res = await fetch(`${API_BASE}/citation_bias?url=${encodeURIComponent(url)}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// Article Preview
export interface ArticlePreview {
  url: string;
  title: string;
  content: string;
  domain: string;
  error?: string;
}

export async function fetchArticlePreview(url: string): Promise<ArticlePreview> {
  const res = await fetch(`${API_BASE}/fetch-article?url=${encodeURIComponent(url)}`);
  if (!res.ok) {
    throw new Error("Failed to fetch article");
  }
  return res.json();
}

// Article Summary
export interface ArticleSummary {
  summary: string;
  error?: string;
}

export async function fetchArticleSummary(content: string, title?: string): Promise<ArticleSummary> {
  const res = await fetch(`${API_BASE}/summarize-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, title }),
  });
  if (!res.ok) {
    throw new Error("Failed to fetch summary");
  }
  return res.json();
}

// Article Graph
export interface GraphNode {
  id: string;
  title: string;
  citation_count: number;
  outgoing_links: number;
  citation_domains_count?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  types: string[];
  metadata?: {
    shared_citations?: string[];
    shared_domains?: string[];
    link_direction?: string[];
    co_linked_targets?: string[];
  };
}

export interface ArticleGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center_node?: string | null;
  stats?: {
    total_nodes: number;
    total_edges: number;
    edges_by_type?: Record<string, number>;
  };
}

export async function getArticleGraph(articleId?: string): Promise<ArticleGraph> {
  let url = `${API_BASE}/article_graph`;
  if (articleId) {
    url += `?article_id=${encodeURIComponent(articleId)}`;
  }
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error("Failed to load article graph");
  }
  return res.json();
}
