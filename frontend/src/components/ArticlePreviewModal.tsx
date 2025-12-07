import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { fetchArticlePreview, fetchArticleSummary } from "../api";
import type { ArticlePreview } from "../api";

interface Props {
  isOpen: boolean;
  url: string;
  onClose: () => void;
}

export default function ArticlePreviewModal({ isOpen, url, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [article, setArticle] = useState<ArticlePreview | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !url) return;

    setLoading(true);
    setArticle(null);
    setSummary(null);

    fetchArticlePreview(url)
      .then((data) => {
        setArticle(data);
        setLoading(false);

        // Fetch summary if content was successfully loaded
        if (data.content && !data.error) {
          setSummaryLoading(true);
          fetchArticleSummary(data.content, data.title)
            .then((res) => {
              if (res.summary && !res.error) {
                setSummary(res.summary);
              }
            })
            .catch(() => {
              // Silently fail - summary is optional
            })
            .finally(() => setSummaryLoading(false));
        }
      })
      .catch(() => {
        setArticle({
          url,
          title: "Error",
          content: "",
          domain: "",
          error: "Failed to fetch the article. Please try again.",
        });
        setLoading(false);
      });
  }, [isOpen, url]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="modal-backdrop" onClick={handleBackdropClick}>
      <div className="modal-dialog article-preview-modal">
        <div className="modal-header">
          <div className="article-preview-title">
            {loading ? (
              <span className="loading-text">Loading...</span>
            ) : (
              <>
                <h2>{article?.title || "Article Preview"}</h2>
                {article?.domain && (
                  <span className="article-domain">{article.domain}</span>
                )}
              </>
            )}
          </div>
          <button className="modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="modal-body article-preview-content">
          {loading ? (
            <div className="loading-spinner">
              <div className="spinner" />
              <p>Fetching article content...</p>
            </div>
          ) : article?.error ? (
            <div className="article-error">
              <p>{article.error}</p>
            </div>
          ) : (
            <>
              {/* Grokipedia Summary Section */}
              <div className="grokipedia-summary">
                <div className="grokipedia-summary-header">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5" />
                    <path d="M2 12l10 5 10-5" />
                  </svg>
                  <span>Grokipedia Summary</span>
                </div>
                <div className="grokipedia-summary-content">
                  {summaryLoading ? (
                    <div className="summary-loading">
                      <span className="summary-spinner" />
                      <span>Generating summary...</span>
                    </div>
                  ) : summary ? (
                    <p>{summary}</p>
                  ) : (
                    <p className="summary-unavailable">Summary unavailable</p>
                  )}
                </div>
              </div>

              {/* Article Content */}
              <ReactMarkdown>{article?.content || ""}</ReactMarkdown>
            </>
          )}
        </div>

        <div className="modal-footer">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="open-original-link"
          >
            Open original article &rarr;
          </a>
        </div>
      </div>
    </div>
  );
}
