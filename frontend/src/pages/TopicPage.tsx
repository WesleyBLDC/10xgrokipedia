import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { getTopic, getSuggestions } from "../api";
import type { Topic, Suggestion } from "../api";
import SuggestEditModal from "../components/SuggestEditModal";
import SuggestionsPanel from "../components/SuggestionsPanel";
import VersionHistory from "../components/VersionHistory";
import CommunityFeed from "../components/CommunityFeed";
import { getAggregateBias } from "../api";
import type { AggregateBias } from "../api";

export default function TopicPage() {
  const { topic } = useParams<{ topic: string }>();
  const [data, setData] = useState<Topic | null>(null);
  const [biasData, setBiasData] = useState<AggregateBias | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const navigate = useNavigate();

  // Version history state
  const [viewingVersionIndex, setViewingVersionIndex] = useState<number | null>(null);
  const [versionContent, setVersionContent] = useState<string | null>(null);

  // Text selection state
  const [selectedText, setSelectedText] = useState("");
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null);
  const [showModal, setShowModal] = useState(false);

  // Footnote tracking
  const footnoteCounter = useRef(0);
  const footnoteMap = useRef<Map<string, number>>(new Map());

  const loadData = useCallback(async () => {
    if (!topic) return;
    setData(null);
    setError(null);
    setViewingVersionIndex(null);
    setVersionContent(null);
    footnoteCounter.current = 0;
    footnoteMap.current.clear();

    try {
      const [topicData, suggestionsData] = await Promise.all([
        getTopic(topic),
        getSuggestions(topic),
      ]);
      setData(topicData);
      setSuggestions(suggestionsData);
    } catch {
      setError("Topic not found");
    }
  }, [topic]);

  useEffect(() => {
    if (topic) {
      setData(null);
      setBiasData(null);
      setError(null);
      setViewingVersionIndex(null);
      setVersionContent(null);
      footnoteCounter.current = 0;
      footnoteMap.current.clear();
      getTopic(topic)
        .then(setData)
        .catch(() => setError("Topic not found"));
      // Bias data is fetched by the separate version-aware effect
    }
  }, [topic]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const getFootnoteNumber = (url: string): number => {
    if (footnoteMap.current.has(url)) {
      return footnoteMap.current.get(url)!;
    }
    footnoteCounter.current += 1;
    footnoteMap.current.set(url, footnoteCounter.current);
    return footnoteCounter.current;
  };

  const handleMouseUp = () => {
    // Don't allow text selection for edits when viewing old versions
    if (viewingVersionIndex !== null) return;

    const selection = window.getSelection();
    if (selection && selection.toString().trim().length > 0) {
      const text = selection.toString().trim();
      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();

      setSelectedText(text);
      setTooltipPosition({
        x: rect.left + rect.width / 2,
        y: rect.top - 10,
      });
    } else {
      setTooltipPosition(null);
    }
  };

  const handleSuggestEdit = () => {
    setShowModal(true);
    setTooltipPosition(null);
  };

  const handleModalClose = () => {
    setShowModal(false);
    setSelectedText("");
  };

  const handleSuggestionSuccess = () => {
    loadData();
  };

  const handleVersionSelect = (content: string | null, versionIndex: number | null) => {
    setViewingVersionIndex(versionIndex);
    setVersionContent(content);
  };

  // Fetch bias data when topic or version changes
  useEffect(() => {
    if (!topic) return;

    getAggregateBias(topic, viewingVersionIndex ?? undefined)
      .then(setBiasData)
      .catch(() => {
        setBiasData(null);
      });
  }, [topic, viewingVersionIndex]);

  const pendingCount = suggestions.filter(s => s.status === "pending" || s.status === "reviewed").length;
  const totalCount = suggestions.length;

  // Content to display (version or current)
  const displayContent = versionContent ?? data?.content ?? "";

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
        <div className="topic-header">
            <Link to="/" className="back-link">← Back to search</Link>
            <div className="header-actions">
            <VersionHistory
                topicSlug={topic!}
                onVersionSelect={handleVersionSelect}
                currentVersionIndex={viewingVersionIndex}
            />
            {totalCount > 0 && (
                <button
                className={`suggestions-badge ${pendingCount === 0 ? "no-pending" : ""}`}
                onClick={() => setShowSuggestions(!showSuggestions)}
                >
                {pendingCount > 0
                    ? `${pendingCount} pending edit${pendingCount !== 1 ? "s" : ""}`
                    : `${totalCount} edit${totalCount !== 1 ? "s" : ""}`}
                </button>
            )}
            </div>
      </div>

      {versionContent && (
        <div className="version-banner">
          <span>Viewing an older version of this article</span>
          <button onClick={() => handleVersionSelect(null, null)}>Return to current</button>
        </div>
      )}

      <h1>{data.title}</h1>


      <div className="topic-layout">
        {/* Left column: Community Feed and future components */}
        <aside className="left-rail">
          {topic && <CommunityFeed topicSlug={topic} />}
        </aside>

        {/* Right column: Edit history + article content */}
        <main className="main-content">
          {showSuggestions && !versionContent && (
            <SuggestionsPanel
              suggestions={suggestions}
              topicSlug={topic!}
              onUpdate={loadData}
            />
          )}
          <div className="topic-header">
            {biasData && (
            <div className="bias-marker">
                <div className="bias-score">
                <span className="bias-label">Factuality:</span>
                <span className={`bias-value factual ${biasData.factual_label.toLowerCase().replace(/\s+/g, '-')}`}>
                    {biasData.factual_label}
                </span>
                </div>
                <div className="bias-score">
                <span className="bias-label">Source Bias:</span>
                <div className="bias-bar-container">
                    <div className="bias-bar">
                    <div 
                        className="bias-dot"
                        style={{
                        left: `${((biasData.average_bias_score + 10) / 20) * 100}%`
                        }}
                    />
                    </div>
                </div>
                </div>
                {biasData.evaluated_citation_count > 0 && (
                <div className="bias-meta">
                    Based on {biasData.evaluated_citation_count} of {biasData.citation_count} citations
                </div>
                )}
            </div>
            )}
          </div>

          <div className="content" onMouseUp={handleMouseUp}>
            <ReactMarkdown
              components={{
                a: ({ href, children }) => {
                  const hasText = children &&
                    (typeof children === 'string' ? children.trim() :
                      Array.isArray(children) ? children.some(c => c) : true);

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

                  return (
                    <a href={href} target="_blank" rel="noopener noreferrer">
                      {children}
                    </a>
                  );
                },
              }}
            >
              {displayContent}
            </ReactMarkdown>
          </div>
        </main>
      </div>

      {tooltipPosition && !versionContent && (
        <button
          className="suggest-edit-tooltip"
          style={{
            position: "fixed",
            left: tooltipPosition.x,
            top: tooltipPosition.y,
            transform: "translate(-50%, -100%)",
          }}
          onClick={handleSuggestEdit}
        >
          Suggest Edit
        </button>
      )}

      <SuggestEditModal
        isOpen={showModal}
        onClose={handleModalClose}
        selectedText={selectedText}
        topicSlug={topic!}
        onSuccess={handleSuggestionSuccess}
      />
    </div>
  );
}

