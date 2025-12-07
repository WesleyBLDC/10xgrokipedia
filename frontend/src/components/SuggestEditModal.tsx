import { useState } from "react";
import { submitSuggestion } from "../api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  selectedText: string;
  articleId: string;
  onSuccess: () => void;
}

export default function SuggestEditModal({ isOpen, onClose, selectedText, articleId, onSuccess }: Props) {
  const [summary, setSummary] = useState("");
  const [sources, setSources] = useState<string[]>([""]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleAddSource = () => {
    setSources([...sources, ""]);
  };

  const handleSourceChange = (index: number, value: string) => {
    const newSources = [...sources];
    newSources[index] = value;
    setSources(newSources);
  };

  const handleSubmit = async () => {
    if (!summary.trim()) {
      setError("Please provide a summary of your suggested change");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await submitSuggestion(articleId, {
        highlighted_text: selectedText,
        summary: summary.trim(),
        sources: sources.filter(s => s.trim()),
      });
      setSummary("");
      setSources([""]);
      onSuccess();
      onClose();
    } catch {
      setError("Failed to submit suggestion. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="modal-backdrop" onClick={handleBackdropClick}>
      <div className="modal-dialog">
        <div className="modal-header">
          <h2>Suggest an edit</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <p className="modal-description">
          Help improve this article by suggesting changes. Your edit will be reviewed before being published.
        </p>

        <div className="modal-body">
          <div className="form-group">
            <label>Selected text</label>
            <div className="selected-text">"{selectedText}"</div>
          </div>

          <div className="form-group">
            <label htmlFor="summary">Summary</label>
            <textarea
              id="summary"
              placeholder="Briefly describe your changes (e.g., 'Updated birth year to 1990')"
              rows={3}
              maxLength={1500}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>Supporting sources (optional)</label>
            {sources.map((source, index) => (
              <input
                key={index}
                type="url"
                placeholder="https://example.com/source"
                value={source}
                onChange={(e) => handleSourceChange(index, e.target.value)}
              />
            ))}
            <button type="button" className="add-source-btn" onClick={handleAddSource}>
              + Add another source
            </button>
          </div>

          {error && <p className="modal-error">{error}</p>}

          <button
            className="submit-btn"
            onClick={handleSubmit}
            disabled={submitting || !summary.trim()}
          >
            {submitting ? "Submitting..." : "Submit Edit"}
          </button>
        </div>
      </div>
    </div>
  );
}
