import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { searchTopics } from "../api";
import type { TopicSummary } from "../api";

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TopicSummary[]>([]);
  const navigate = useNavigate();

  const handleSearch = async (value: string) => {
    setQuery(value);
    if (value.trim()) {
      const data = await searchTopics(value);
      setResults(data);
    } else {
      setResults([]);
    }
  };

  return (
    <div className="home">
      <h1>10xGrokipedia</h1>
      <p className="subtitle">The AI-powered encyclopedia</p>
      <div className="search-container">
        <input
          type="text"
          className="search-input"
          placeholder="Search for a topic..."
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          autoFocus
        />
      </div>
      <button
        onClick={() => navigate("/graph")}
        className="version-history-btn"
        style={{ marginTop: "1rem" }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3" />
          <circle cx="5" cy="5" r="2" />
          <circle cx="19" cy="5" r="2" />
          <circle cx="5" cy="19" r="2" />
          <circle cx="19" cy="19" r="2" />
          <line x1="5" y1="5" x2="12" y2="12" />
          <line x1="19" y1="5" x2="12" y2="12" />
          <line x1="5" y1="19" x2="12" y2="12" />
          <line x1="19" y1="19" x2="12" y2="12" />
        </svg>
        Explore Article Graph
      </button>
      {results.length > 0 && (
        <ul className="results">
          {results.map((r) => (
            <li key={r.id} onClick={() => navigate(`/page/${r.id}`)}>
              {r.title}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
