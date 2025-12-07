import { useState, useEffect, useRef } from "react";
import { getVersions, getVersion } from "../api";
import type { VersionSummary } from "../api";

interface Props {
  topicSlug: string;
  onVersionSelect: (content: string | null) => void;
  currentVersionIndex: number | null;
}

export default function VersionHistory({ topicSlug, onVersionSelect, currentVersionIndex }: Props) {
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState<number | null>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loadVersions = async () => {
      try {
        const data = await getVersions(topicSlug);
        setVersions(data);
      } catch (err) {
        console.error("Failed to load versions:", err);
      }
    };
    loadVersions();
  }, [topicSlug]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleVersionClick = async (index: number) => {
    setLoading(index);
    try {
      const versionData = await getVersion(topicSlug, index);
      onVersionSelect(versionData.content);
      setIsOpen(false);
    } catch (err) {
      console.error("Failed to load version:", err);
    } finally {
      setLoading(null);
    }
  };

  const handleCurrentClick = () => {
    onVersionSelect(null);
    setIsOpen(false);
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  const formatRelativeTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return formatDate(timestamp);
  };

  if (versions.length === 0) {
    return null;
  }

  return (
    <div className="version-history" ref={dropdownRef}>
      <button
        className={`version-history-btn ${currentVersionIndex !== null ? "viewing-old" : ""}`}
        onClick={() => setIsOpen(!isOpen)}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <polyline points="12,6 12,12 16,14" />
        </svg>
        {versions.length} version{versions.length !== 1 ? "s" : ""}
      </button>

      {isOpen && (
        <div className="version-dropdown">
          <div className="version-dropdown-header">Version History</div>
          <div className="version-timeline">
            {/* Current version */}
            <div
              className={`version-item ${currentVersionIndex === null ? "active" : ""}`}
              onClick={handleCurrentClick}
            >
              <div className="version-dot current" />
              <div className="version-info">
                <span className="version-label">Current Version</span>
                <span className="version-time">Latest</span>
              </div>
            </div>

            {/* Historical versions (newest first) */}
            {[...versions].reverse().map((v, idx) => {
              const actualIndex = versions.length - 1 - idx;
              return (
                <div
                  key={v.index}
                  className={`version-item ${currentVersionIndex === actualIndex ? "active" : ""}`}
                  onClick={() => handleVersionClick(actualIndex)}
                  onMouseEnter={() => setHoveredIndex(actualIndex)}
                  onMouseLeave={() => setHoveredIndex(null)}
                >
                  <div className="version-dot" />
                  <div className="version-info">
                    <span className="version-label">
                      Version {actualIndex + 1}
                      {loading === actualIndex && " (Loading...)"}
                    </span>
                    <span className="version-time">
                      {hoveredIndex === actualIndex ? formatDate(v.timestamp) : formatRelativeTime(v.timestamp)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
