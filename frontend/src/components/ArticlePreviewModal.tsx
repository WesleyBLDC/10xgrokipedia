import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { fetchArticlePreview } from "../api";
import type { ArticlePreview } from "../api";

interface Props {
  isOpen: boolean;
  url: string;
  onClose: () => void;
}

export default function ArticlePreviewModal({ isOpen, url, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [article, setArticle] = useState<ArticlePreview | null>(null);

  useEffect(() => {
    if (!isOpen || !url) return;

    setLoading(true);
    setArticle(null);

    fetchArticlePreview(url)
      .then(setArticle)
      .catch(() => {
        setArticle({
          url,
          title: "Error",
          content: "",
          domain: "",
          error: "Failed to fetch the article. Please try again.",
        });
      })
      .finally(() => setLoading(false));
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
            <ReactMarkdown>{article?.content || ""}</ReactMarkdown>
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
