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
      <p className="subtitle">Truthseeker's encyclopedia</p>
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
      {results.length > 0 && (
        <ul className="results">
          {results.map((r) => (
            <li key={r.topic} onClick={() => navigate(`/page/${r.topic}`)}>
              {r.title}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
