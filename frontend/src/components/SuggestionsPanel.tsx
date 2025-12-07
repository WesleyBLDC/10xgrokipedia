import { useState } from "react";
import { reviewSuggestion, applySuggestion, rejectSuggestion } from "../api";
import type { Suggestion, ReviewResult } from "../api";

interface Props {
  suggestions: Suggestion[];
  articleId: string;
  onUpdate: () => void;
}

interface ReviewModalState {
  isOpen: boolean;
  suggestionId: string | null;
  result: ReviewResult | null;
}

export default function SuggestionsPanel({ suggestions, articleId, onUpdate }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [applying, setApplying] = useState<string | null>(null);
  const [reviewModal, setReviewModal] = useState<ReviewModalState>({
    isOpen: false,
    suggestionId: null,
    result: null,
  });

  const handleReview = async (id: string) => {
    setReviewing(id);
    try {
      const result = await reviewSuggestion(articleId, id);
      // Show the modal with the result
      setReviewModal({
        isOpen: true,
        suggestionId: id,
        result,
      });
      onUpdate();
    } catch (err) {
      console.error("Review failed:", err);
    } finally {
      setReviewing(null);
    }
  };

  const handleApply = async (id: string) => {
    setApplying(id);
    try {
      await applySuggestion(articleId, id);
      setReviewModal({ isOpen: false, suggestionId: null, result: null });
      onUpdate();
    } catch (err) {
      console.error("Apply failed:", err);
    } finally {
      setApplying(null);
    }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectSuggestion(articleId, id);
      setReviewModal({ isOpen: false, suggestionId: null, result: null });
      onUpdate();
    } catch (err) {
      console.error("Reject failed:", err);
    }
  };

  const closeModal = () => {
    setReviewModal({ isOpen: false, suggestionId: null, result: null });
  };

  const pendingCount = suggestions.filter(s => s.status === "pending" || s.status === "reviewed").length;

  if (suggestions.length === 0) {
    return null;
  }

  return (
    <>
      <div className="suggestions-panel">
        <h3>
          Edit History
          {pendingCount > 0 && <span className="pending-count"> ({pendingCount} pending)</span>}
        </h3>
        <div className="suggestions-list">
          {suggestions.map((s) => (
            <div key={s.id} className="suggestion-item">
              <div
                className="suggestion-header"
                onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}
              >
                <span className="suggestion-summary">{s.summary}</span>
                <span className={`suggestion-status status-${s.status}`}>
                  {s.status}
                </span>
              </div>

              {expandedId === s.id && (
                <div className="suggestion-details">
                  <div className="detail-row">
                    <strong>Highlighted text:</strong>
                    <p>"{s.highlighted_text}"</p>
                  </div>

                  {s.sources.length > 0 && (
                    <div className="detail-row">
                      <strong>Sources:</strong>
                      <ul>
                        {s.sources.map((src, i) => (
                          <li key={i}>
                            <a href={src} target="_blank" rel="noopener noreferrer">
                              {src}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {s.review_result && (
                    <div className={`review-result ${s.review_result.approved ? "approved" : "rejected"}`}>
                      <strong>AI Review:</strong>
                      <p className="reasoning">{s.review_result.reasoning}</p>
                      {s.review_result.suggested_content && (
                        <div className="suggested-content">
                          <strong>Suggested replacement:</strong>
                          <p>"{s.review_result.suggested_content}"</p>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="suggestion-actions">
                    {s.status === "pending" && (
                      <>
                        <button
                          className="btn-review"
                          onClick={() => handleReview(s.id)}
                          disabled={reviewing === s.id}
                        >
                          {reviewing === s.id ? "Reviewing..." : "Review with AI"}
                        </button>
                        <button
                          className="btn-reject"
                          onClick={() => handleReject(s.id)}
                        >
                          Reject
                        </button>
                      </>
                    )}

                    {s.status === "reviewed" && (
                      <>
                        {s.review_result?.approved && (
                          <button
                            className="btn-apply"
                            onClick={() => handleApply(s.id)}
                            disabled={applying === s.id}
                          >
                            {applying === s.id ? "Applying..." : "Apply Edit"}
                          </button>
                        )}
                        <button
                          className="btn-reject"
                          onClick={() => handleReject(s.id)}
                        >
                          Reject
                        </button>
                      </>
                    )}

                    {s.status === "applied" && (
                      <span className="status-label status-applied">Applied</span>
                    )}

                    {s.status === "rejected" && (
                      <span className="status-label status-rejected">Rejected</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Review Result Modal */}
      {reviewModal.isOpen && reviewModal.result && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && closeModal()}>
          <div className="modal-dialog review-modal">
            <div className="modal-header">
              <h2>AI Review Result</h2>
              <button className="modal-close" onClick={closeModal}>×</button>
            </div>

            <div className="review-verdict">
              <span className={`verdict-badge ${reviewModal.result.approved ? "approved" : "rejected"}`}>
                {reviewModal.result.approved ? "✓ Approved" : "✗ Not Approved"}
              </span>
            </div>

            <div className="modal-body">
              <div className="form-group">
                <label>AI Reasoning</label>
                <p className="review-reasoning">{reviewModal.result.reasoning}</p>
              </div>

              {reviewModal.result.suggested_content && (
                <div className="form-group">
                  <label>Suggested Replacement Text</label>
                  <div className="suggested-text">"{reviewModal.result.suggested_content}"</div>
                </div>
              )}

              <div className="modal-actions">
                {reviewModal.result.approved && (
                  <button
                    className="btn-apply"
                    onClick={() => reviewModal.suggestionId && handleApply(reviewModal.suggestionId)}
                    disabled={applying === reviewModal.suggestionId}
                  >
                    {applying === reviewModal.suggestionId ? "Applying..." : "Apply Edit"}
                  </button>
                )}
                <button
                  className="btn-reject"
                  onClick={() => reviewModal.suggestionId && handleReject(reviewModal.suggestionId)}
                >
                  Reject
                </button>
                <button className="btn-close" onClick={closeModal}>
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
