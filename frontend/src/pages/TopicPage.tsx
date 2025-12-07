import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { useParams, Link, useNavigate, useLocation } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { getTopic, getSuggestions, getCitationBias } from "../api";
import type { Topic, Suggestion, CitationBias } from "../api";
import rehypeRaw from "rehype-raw";
import SuggestEditModal from "../components/SuggestEditModal";
import SuggestionsPanel from "../components/SuggestionsPanel";
import VersionHistory from "../components/VersionHistory";
import CommunityFeed from "../components/CommunityFeed";
import { getAggregateBias } from "../api";
import type { AggregateBias } from "../api";

type ContradictionEntry = {
  article_a_title: string;
  article_a_url: string;
  claim_a: string;
  claim_a_offset?: { start: number; end: number; line: number };
  article_b_title: string;
  article_b_url: string;
  claim_b: string;
  claim_b_offset?: { start: number; end: number; line: number };
  difference: string;
};

type ContradictionCluster = {
  cluster_id: number;
  members: { url: string; title: string; slug: string }[];
  parsed?: { contradictions?: ContradictionEntry[] };
};

export default function TopicPage() {
  const { topic } = useParams<{ topic: string }>();
  const location = useLocation();
  const [data, setData] = useState<Topic | null>(null);
  const [biasData, setBiasData] = useState<AggregateBias | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [showContradictions, setShowContradictions] = useState(false);
  const [contradictionData, setContradictionData] = useState<ContradictionCluster[] | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  // Version history state
  const [viewingVersionIndex, setViewingVersionIndex] = useState<number | null>(null);
  const [versionContent, setVersionContent] = useState<string | null>(null);

  // Text selection state
  const [selectedText, setSelectedText] = useState("");
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null);
  const [showModal, setShowModal] = useState(false);

  // Citation hover state
  const [citationTooltip, setCitationTooltip] = useState<{
    url: string;
    data: CitationBias;
    position: { x: number; y: number };
  } | null>(null);
  const citationTooltipTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Load contradiction JSON once (served as static asset)
  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/contradictions_llm.json");
        if (res.ok) {
          const json = await res.json();
          setContradictionData(json);
        }
      } catch (e) {
        console.warn("Failed to load contradictions JSON", e);
      }
    };
    load();
  }, []);

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
  const focusClaim = (location.state as { focusClaim?: string } | null)?.focusClaim ?? null;

  // Build a list of contradictions relevant to this article (by URL/slug match)
  const relevantContradictions = useMemo(() => {
    if (!contradictionData || !data) return [];
    const slugUrl = `https://grokipedia.com/page/${topic}`;
    const matches: ContradictionEntry[] = [];
    for (const cluster of contradictionData) {
      const list = cluster.parsed?.contradictions ?? [];
      for (const c of list) {
        if (c.article_a_url === slugUrl || c.article_b_url === slugUrl) {
          matches.push(c);
        }
      }
    }
    return matches;
  }, [contradictionData, data, topic]);

  // Apply highlights to the markdown content using offsets or substring search
  const highlightedContent = useMemo(() => {
    if (!showContradictions || relevantContradictions.length === 0 || !displayContent) {
      return displayContent;
    }

    type Range = {
      start: number;
      end: number;
      html: string;
    };

    const ranges: Range[] = [];
    const slugUrl = `https://grokipedia.com/page/${topic}`;

    const addRange = (
      start: number,
      end: number,
      myClaim: string,
      otherTitle: string,
      otherUrl: string,
      otherClaim: string,
      diff: string
    ) => {
      if (start < 0 || end <= start || end > displayContent.length) return;
      const tooltip = `${diff} | See: ${otherTitle}`;
      const safeTitle = tooltip.replace(/"/g, "&quot;").replace(/'/g, "&apos;");
      const safeOtherUrl = otherUrl.replace(/"/g, "&quot;");
      const safeOtherClaim = otherClaim.replace(/"/g, "&quot;").replace(/'/g, "&apos;");
      const safeMyClaim = myClaim.replace(/"/g, "&quot;").replace(/'/g, "&apos;");
      const inlineStyle = "border-bottom: 2px solid rgba(239,68,68,0.6); background: rgba(239,68,68,0.05); cursor: pointer;";
      ranges.push({
        start,
        end,
        html: `<span class="contradiction-highlight" style="${inlineStyle}" title="${safeTitle}" data-target="${safeOtherUrl}" data-target-claim="${safeOtherClaim}" data-claim-text="${safeMyClaim}">`,
      });
    };

    const findOrOffset = (claim: string, offset?: { start: number; end: number }) => {
      if (offset && offset.start >= 0 && offset.end > offset.start) return offset;
      const idx = displayContent.indexOf(claim);
      if (idx === -1) {
        console.warn("Could not find exact claim in content:", claim.substring(0, 100));
        return null;
      }
      return { start: idx, end: idx + claim.length };
    };

    for (const c of relevantContradictions) {
      const isA = c.article_a_url === slugUrl;
      const myClaim = isA ? c.claim_a : c.claim_b;
      const myOffset = isA ? c.claim_a_offset : c.claim_b_offset;
      const otherClaim = isA ? c.claim_b : c.claim_a;
      const otherTitle = isA ? c.article_b_title : c.article_a_title;
      const otherUrl = isA ? c.article_b_url : c.article_a_url;
      const off = findOrOffset(myClaim, myOffset);
      if (!off) {
        console.warn("Could not find claim:", myClaim, "in content");
        continue;
      }
      console.log("Adding highlight:", { start: off.start, end: off.end, claim: myClaim });
      addRange(off.start, off.end, myClaim, otherTitle, otherUrl, otherClaim, c.difference);
    }

    if (ranges.length === 0) {
      console.log("No ranges to highlight for", slugUrl, "relevant:", relevantContradictions);
      return displayContent;
    }

    console.log("Applying", ranges.length, "highlights");

    // Sort and dedupe overlaps (simple non-overlap insertion)
    ranges.sort((a, b) => a.start - b.start || a.end - b.end);
    const merged: Range[] = [];
    let lastEnd = -1;
    for (const r of ranges) {
      if (r.start < lastEnd) continue; // skip overlaps
      merged.push(r);
      lastEnd = r.end;
    }

    // Build final string by injecting spans
    let result = "";
    let cursor = 0;
    for (const r of merged) {
      result += displayContent.slice(cursor, r.start);
      result += r.html;
      result += displayContent.slice(r.start, r.end);
      result += "</span>";
      cursor = r.end;
    }
    result += displayContent.slice(cursor);
    return result;
  }, [showContradictions, relevantContradictions, displayContent, topic]);

  // When arriving from another article with a target claim, auto-enable highlights and scroll to it
  useEffect(() => {
    if (!focusClaim) return;
    if (!showContradictions) {
      setShowContradictions(true);
      return; // wait for highlights to render
    }
    const container = contentRef.current;
    if (!container) return;
    // Find the highlighted span that matches the target claim text
    const spans = Array.from(container.querySelectorAll<HTMLElement>(".contradiction-highlight"));
    const match = spans.find(el => el.dataset.claimText === focusClaim);
    if (match) {
      match.scrollIntoView({ behavior: "smooth", block: "center" });
      match.classList.add("contradiction-highlight-flash");
      setTimeout(() => match.classList.remove("contradiction-highlight-flash"), 1200);
    }
  }, [focusClaim, showContradictions, highlightedContent]);

  // Click handler for contradiction highlights: navigate to the other article
  const handleContentClick = useCallback((evt: React.MouseEvent<HTMLDivElement>) => {
    const target = (evt.target as HTMLElement).closest(".contradiction-highlight") as HTMLElement | null;
    if (!target) return;

    evt.preventDefault();
    evt.stopPropagation();
    const otherUrl = target.getAttribute("data-target");
    const otherClaim = target.getAttribute("data-target-claim");
    if (!otherUrl) return;

    const slugMatch = otherUrl.match(/\/page\/(.+)$/);
    if (slugMatch) {
      const slug = slugMatch[1];
      navigate(`/page/${slug}`, {
        state: { focusClaim: otherClaim ?? null },
      });
    } else {
      window.open(otherUrl, "_blank");
    }
  }, [navigate]);

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
          <button
            className={`toggle-contradictions ${showContradictions ? "active" : ""}`}
            onClick={() => setShowContradictions(!showContradictions)}
            disabled={versionContent !== null}
            title={
              versionContent
                ? "Highlights disabled when viewing older version"
                : "Toggle contradiction highlights. Click any red underline to jump to the conflicting line in the other article."
            }
          >
            <span className="toggle-label">
              {showContradictions ? "Hide contradictions" : "Show contradictions"}
            </span>
            {relevantContradictions.length > 0 && (
              <span className="contradiction-badge" aria-label={`${relevantContradictions.length} contradictions`}>
                {relevantContradictions.length}
              </span>
            )}
          </button>
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

          <div className="content" onMouseUp={handleMouseUp} onClick={handleContentClick} ref={contentRef}>
            <ReactMarkdown
              rehypePlugins={[rehypeRaw]}
              skipHtml={false}
              components={{
                a: ({ href, children }) => {
                  const hasText = children &&
                    (typeof children === 'string' ? children.trim() :
                      Array.isArray(children) ? children.some(c => c) : true);

                  if (!hasText && href) {
                    const num = getFootnoteNumber(href);
                    const isExternalCitation = href && (href.startsWith('http://') || href.startsWith('https://'));
                    
                    const handleCitationMouseEnter = async (e: React.MouseEvent<HTMLAnchorElement>) => {
                      if (!isExternalCitation) return;
                      
                      // Clear any existing timeout
                      if (citationTooltipTimeoutRef.current) {
                        clearTimeout(citationTooltipTimeoutRef.current);
                      }
                      
                      const rect = e.currentTarget.getBoundingClientRect();
                      const biasData = await getCitationBias(href);
                      
                      // Show tooltip even if no data, with "Unknown" values
                      setCitationTooltip({
                        url: href,
                        data: biasData || {
                          citation_url: href,
                          factual_score: 0,
                          factual_label: "Unknown",
                          bias_score: 0,
                          bias_label: "Unknown",
                        },
                        position: {
                          x: rect.left + rect.width / 2,
                          y: rect.top - 8,
                        },
                      });
                    };
                    
                    const handleCitationMouseLeave = () => {
                      // Delay hiding to allow moving to tooltip
                      citationTooltipTimeoutRef.current = setTimeout(() => {
                        setCitationTooltip(null);
                      }, 200);
                    };
                    
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="footnote"
                        title={href}
                        onMouseEnter={handleCitationMouseEnter}
                        onMouseLeave={handleCitationMouseLeave}
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

                  // External links with text - also check if they're citations
                  const isExternalCitation = href && (href.startsWith('http://') || href.startsWith('https://'));
                  
                  const handleLinkMouseEnter = async (e: React.MouseEvent<HTMLAnchorElement>) => {
                    if (!isExternalCitation) return;
                    
                    if (citationTooltipTimeoutRef.current) {
                      clearTimeout(citationTooltipTimeoutRef.current);
                    }
                    
                    const rect = e.currentTarget.getBoundingClientRect();
                    const biasData = await getCitationBias(href);
                    
                    // Show tooltip even if no data, with "Unknown" values
                    setCitationTooltip({
                      url: href,
                      data: biasData || {
                        citation_url: href,
                        factual_score: 0,
                        factual_label: "Unknown",
                        bias_score: 0,
                        bias_label: "Unknown",
                      },
                      position: {
                        x: rect.left + rect.width / 2,
                        y: rect.top - 8,
                      },
                    });
                  };
                  
                  const handleLinkMouseLeave = () => {
                    citationTooltipTimeoutRef.current = setTimeout(() => {
                      setCitationTooltip(null);
                    }, 200);
                  };

                  return (
                    <a 
                      href={href} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      onMouseEnter={handleLinkMouseEnter}
                      onMouseLeave={handleLinkMouseLeave}
                    >
                      {children}
                    </a>
                  );
                },
              }}
            >
              {highlightedContent}
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

      {citationTooltip && (
        <div
          className="citation-bias-tooltip"
          style={{
            position: "fixed",
            left: citationTooltip.position.x,
            top: citationTooltip.position.y,
            transform: "translate(-50%, -100%)",
          }}
          onMouseEnter={() => {
            if (citationTooltipTimeoutRef.current) {
              clearTimeout(citationTooltipTimeoutRef.current);
            }
          }}
          onMouseLeave={() => {
            citationTooltipTimeoutRef.current = setTimeout(() => {
              setCitationTooltip(null);
            }, 200);
          }}
        >
          <div className="citation-bias-tooltip-content">
            <div className="citation-bias-row">
              <span className="citation-bias-label">Factuality:</span>
              <span className={`citation-bias-value factual ${citationTooltip.data.factual_label.toLowerCase().replace(/\s+/g, '-')}`}>
                {citationTooltip.data.factual_label}
              </span>
            </div>
            <div className="citation-bias-row">
              <span className="citation-bias-label">Bias:</span>
              <span className={`citation-bias-value bias ${citationTooltip.data.bias_label.toLowerCase().replace(/\s+/g, '-')}`}>
                {citationTooltip.data.bias_label}
              </span>
            </div>
          </div>
        </div>
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

