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
  created_at?: string | null;
  like_count?: number | null;
  retweet_count?: number | null;
  reply_count?: number | null;
  quote_count?: number | null;
  url: string;
}

export interface TweetsSummary {
  bullets: string[];
  model?: string | null;
  cached: boolean;
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
