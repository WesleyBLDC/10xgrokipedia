import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getTopic } from "../api";
import type { Topic } from "../api";

export default function TopicPage() {
  const { topic } = useParams<{ topic: string }>();
  const [data, setData] = useState<Topic | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (topic) {
      getTopic(topic)
        .then(setData)
        .catch(() => setError("Topic not found"));
    }
  }, [topic]);

  if (error) {
    return (
      <div className="topic-page">
        <Link to="/" className="back-link">← Back to search</Link>
        <h1>Not Found</h1>
        <p className="error">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="topic-page">
        <p className="loading">Loading...</p>
      </div>
    );
  }

  return (
    <div className="topic-page">
      <Link to="/" className="back-link">← Back to search</Link>
      <h1>{data.title}</h1>
      <div className="content">{data.description}</div>
    </div>
  );
}
