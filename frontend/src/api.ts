const API_BASE = "http://localhost:8000/api";

export interface TopicSummary {
  topic: string;
  title: string;
}

export interface Topic {
  topic: string;
  title: string;
  description: string;
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
