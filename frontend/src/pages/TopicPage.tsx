import { useEffect, useState, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { getTopic } from "../api";
import type { Topic } from "../api";

export default function TopicPage() {
  const { topic } = useParams<{ topic: string }>();
  const [data, setData] = useState<Topic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const footnoteCounter = useRef(0);
  const footnoteMap = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    if (topic) {
      setData(null);
      setError(null);
      footnoteCounter.current = 0;
      footnoteMap.current.clear();
      getTopic(topic)
        .then(setData)
        .catch(() => setError("Topic not found"));
    }
  }, [topic]);

  const getFootnoteNumber = (url: string): number => {
    if (footnoteMap.current.has(url)) {
      return footnoteMap.current.get(url)!;
    }
    footnoteCounter.current += 1;
    footnoteMap.current.set(url, footnoteCounter.current);
    return footnoteCounter.current;
  };

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
      <div className="content">
        <ReactMarkdown
          components={{
            a: ({ href, children }) => {
              const hasText = children &&
                (typeof children === 'string' ? children.trim() :
                  Array.isArray(children) ? children.some(c => c) : true);

              // Empty link - show as footnote
              if (!hasText && href) {
                const num = getFootnoteNumber(href);
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="footnote"
                    title={href}
                  >
                    [{num}]
                  </a>
                );
              }

              // Handle internal /page/ links
              if (href?.startsWith("/page/")) {
                const slug = href.replace("/page/", "");
                return (
                  <a
                    href={href}
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(`/page/${slug}`);
                    }}
                  >
                    {children}
                  </a>
                );
              }

              // External links with text
              return (
                <a href={href} target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              );
            },
          }}
        >
          {data.content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
