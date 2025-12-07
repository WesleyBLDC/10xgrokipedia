const API_BASE = "http://localhost:8000/api";

export interface TopicSummary {
  id: string;  // UUID
  title: string;
}

export interface Topic {
  id: string;  // UUID
  title: string;
  content: string;
  suggestion_count: number;
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

export async function getTopic(articleId: string): Promise<Topic> {
  const res = await fetch(`${API_BASE}/topics/${encodeURIComponent(articleId)}`);
  if (!res.ok) throw new Error("Article not found");
  return res.json();
}

export async function getTopicTweets(articleId: string, maxResults = 10): Promise<TweetItem[]> {
  const res = await fetch(
    `${API_BASE}/topics/${encodeURIComponent(articleId)}/tweets?max_results=${maxResults}`
  );
  if (!res.ok) {
    // Surface error text for better UX
    const msg = await res.text();
    throw new Error(msg || "Failed to load tweets");
  }
  return res.json();
}

export async function getTopicTweetsSummary(articleId: string, maxResults = 10): Promise<TweetsSummary> {
  const res = await fetch(
    `${API_BASE}/topics/${encodeURIComponent(articleId)}/tweets/summary?max_results=${maxResults}`
  );
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || "Failed to load summary");
  }
  return res.json();
}

export async function refreshTopicTweets(articleId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/topics/${encodeURIComponent(articleId)}/tweets/refresh`, {
    method: "POST",
  });
  if (!res.ok && res.status !== 204) {
    const msg = await res.text();
    throw new Error(msg || "Failed to refresh tweets cache");
  }
}

export async function submitSuggestion(articleId: string, suggestion: EditSuggestionInput): Promise<Suggestion> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(articleId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(suggestion),
  });
  if (!res.ok) throw new Error("Failed to submit suggestion");
  return res.json();
}

export async function getSuggestions(articleId: string): Promise<Suggestion[]> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(articleId)}`);
  if (!res.ok) throw new Error("Failed to get suggestions");
  return res.json();
}

export async function reviewSuggestion(articleId: string, suggestionId: string): Promise<ReviewResult> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(articleId)}/review/${suggestionId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to review suggestion");
  return res.json();
}

export async function applySuggestion(articleId: string, suggestionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(articleId)}/apply/${suggestionId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to apply suggestion");
}

export async function rejectSuggestion(articleId: string, suggestionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/suggestions/${encodeURIComponent(articleId)}/reject/${suggestionId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to reject suggestion");
}

export async function getVersions(articleId: string): Promise<VersionSummary[]> {
  const res = await fetch(`${API_BASE}/topics/${encodeURIComponent(articleId)}/versions`);
  if (!res.ok) throw new Error("Failed to get versions");
  return res.json();
}

export async function getVersion(articleId: string, index: number): Promise<VersionDetail> {
  const res = await fetch(`${API_BASE}/topics/${encodeURIComponent(articleId)}/versions/${index}`);
  if (!res.ok) throw new Error("Failed to get version");
  return res.json();
}

export async function getAggregateBias(articleId: string, versionIndex?: number): Promise<AggregateBias | null> {
  try {
    let url = `${API_BASE}/aggregate_bias/${encodeURIComponent(articleId)}`;
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

export interface GraphNode {
  id: string;
  title: string;
  citation_count: number;
  outgoing_links: number;
  citation_domains_count: number;
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
  center_node?: string;
  stats?: {
    total_nodes: number;
    total_edges: number;
    edges_by_type?: Record<string, number>;
  };
}

export async function getArticleGraph(articleId?: string): Promise<ArticleGraph> {
  let url = `${API_BASE}/graph`;
  if (articleId) {
    url += `?article_id=${encodeURIComponent(articleId)}`;
  }
  const res = await fetch(url);
  if (!res.ok) {
    const errorText = await res.text();
    let errorMessage = `Failed to load article graph (${res.status})`;
    try {
      const errorJson = JSON.parse(errorText);
      errorMessage = errorJson.detail || errorMessage;
    } catch {
      errorMessage = errorText || errorMessage;
    }
    throw new Error(errorMessage);
  }
  return res.json();
}
