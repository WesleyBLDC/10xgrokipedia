import { useCallback, useEffect, useMemo, useState } from "react";
import type React from "react";
import type { TweetItem, SearchResult, SearchHints } from "../api";
import { getTopicTweets, getTopicTweetsSummary, refreshTopicTweets, searchTweets } from "../api";

interface Props {
  topicSlug: string;
  searchQuery?: string;
  onClearSearch?: () => void;
}

export default function CommunityFeed({ topicSlug, searchQuery, onClearSearch }: Props) {
  const [tweets, setTweets] = useState<TweetItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [summary, setSummary] = useState<string[] | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState<boolean>(false);
  // For smoother transitions, stage the query we render against
  const [activeQuery, setActiveQuery] = useState<string | undefined>(
    searchQuery && searchQuery.trim().length > 0 ? searchQuery : undefined
  );
  const [anim, setAnim] = useState<"idle" | "out" | "in">("idle");
  const [searchHints, setSearchHints] = useState<SearchHints | null>(null);
  const [editingQuery, setEditingQuery] = useState<boolean>(false);
  const [draftQuery, setDraftQuery] = useState<string>("");

  // Derive a small set of readable keywords from the active query
  const keywords = useMemo(() => {
    if (searchHints && searchHints.keywords && searchHints.keywords.length > 0) {
      return searchHints.keywords.map(k => k.toLowerCase());
    }
    if (!activeQuery) return [] as string[];
    const q = activeQuery.toLowerCase();
    // Basic tokenization: letters/numbers/apostrophes/hyphens
    const tokens = q.match(/[\p{L}\p{N}'-]+/gu) || [];
    const STOP = new Set([
      "the","a","an","and","or","but","if","then","else","for","of","in","to","on","at","by","with","as","from","that","this","these","those","is","are","was","were","be","been","being","it","its","into","over","about","after","before","not","no","yes","we","you","they","their","our","his","her","him","she","he","them","which","who","whom","what","when","where","why","how"
    ]);
    const counts = new Map<string, number>();
    for (const t of tokens) {
      const s = t.replace(/^[-']+|[-']+$/g, "");
      if (!s || s.length < 3 || STOP.has(s)) continue;
      counts.set(s, (counts.get(s) || 0) + 1);
    }
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1] || b[0].length - a[0].length);
    return sorted.slice(0, 8).map(([w]) => w);
  }, [activeQuery]);

  const renderHighlightedText = useCallback((text: string, keyPrefix: string): React.ReactNode => {
    if (!keywords.length) return text;
    const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = keywords.map(escape).join("|");
    if (!pattern) return text;
    const regex = new RegExp(`\\b(${pattern})\\b`, "giu");
    const out: React.ReactNode[] = [];
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = regex.exec(text)) !== null) {
      const start = m.index;
      const end = start + m[0].length;
      if (start > last) out.push(text.slice(last, start));
      out.push(
        <span className="cf-keyword" key={`${keyPrefix}-${start}`}>{text.slice(start, end)}</span>
      );
      last = end;
      if (regex.lastIndex === m.index) regex.lastIndex++; // safety
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }, [keywords]);

  // Animate on mode change (topic <-> search)
  useEffect(() => {
    const next = searchQuery && searchQuery.trim().length > 0 ? searchQuery : undefined;
    if (next === activeQuery) return;
    setAnim("out");
    const t1 = setTimeout(() => {
      setActiveQuery(next);
      setAnim("in");
      const t2 = setTimeout(() => setAnim("idle"), 200);
      return () => clearTimeout(t2);
    }, 180);
    return () => clearTimeout(t1);
  }, [searchQuery, activeQuery]);

  const beginQueryChange = useCallback((next: string) => {
    const normNext = (next || "").trim();
    const normCur = (activeQuery || "").trim();
    if (normNext === normCur) return;
    setAnim("out");
    setTimeout(() => {
      setActiveQuery(normNext);
      setAnim("in");
      setTimeout(() => setAnim("idle"), 200);
    }, 180);
  }, [activeQuery]);

  const startEdit = useCallback(() => {
    const seed = (searchHints?.query || activeQuery || "").toString();
    setDraftQuery(seed);
    setEditingQuery(true);
  }, [searchHints, activeQuery]);

  const fetchTweets = useCallback(async (): Promise<TweetItem[] | null> => {
    setLoading(true);
    setError(null);
    setTweets(null);
    let data: TweetItem[] | null = null;
    try {
      if (activeQuery && activeQuery.trim().length > 0) {
        const res: SearchResult = await searchTweets(activeQuery, 10);
        data = res?.tweets || [];
        setTweets(data);
        setSearchHints(res?.hints || null);
      } else {
        data = await getTopicTweets(topicSlug, 10);
        setTweets(data);
        setSearchHints(null);
      }
      return data;
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Failed to load");
      setSearchHints(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, [topicSlug, activeQuery]);

  // Summary is now computed conditionally based on tweets count (see effects/onRefresh)

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTweets(null);
    const run = async () => {
      try {
        if (activeQuery && activeQuery.trim().length > 0) {
          // Search mode: only fetch tweets; no summary
          const res = await searchTweets(activeQuery, 10);
          const data = res?.tweets || [];
          if (!cancelled) {
            setTweets(data);
            setSearchHints(res?.hints || null);
          }
          if (!cancelled) {
            setSummary(null);
            setSummaryError(null);
            setSummaryLoading(false);
          }
        } else {
          // Topic mode: fetch tweets then summary
          const data = await getTopicTweets(topicSlug, 10);
          if (!cancelled) setTweets(data);
          if (!cancelled) setSearchHints(null);
          
          if (data && data.length >= 1) {
            setSummaryLoading(true);
            setSummaryError(null);
            setSummary(null);
            try {
              const s = await getTopicTweetsSummary(topicSlug, 10);
              const bullets = s?.bullets || [];
              // If <=3 tweets, show at most 1 bullet; else show up to 3
              const limited = data.length <= 3 ? bullets.slice(0, 1) : bullets.slice(0, 3);
              if (!cancelled) setSummary(limited);
            } catch (e: any) {
              if (!cancelled) setSummaryError(typeof e?.message === "string" ? e.message : "");
            } finally {
              if (!cancelled) setSummaryLoading(false);
            }
          } else {
            // 0 tweets: no summary
            if (!cancelled) {
              setSummary(null);
              setSummaryError(null);
              setSummaryLoading(false);
            }
          }
        }
      } catch (e: any) {
        if (!cancelled) setError(typeof e?.message === "string" ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [topicSlug, activeQuery]);

  // No explicit truncation hint; use CSS fade/clamp for a cleaner preview

  const onRefresh = async () => {
    try {
      setRefreshing(true);
      if (activeQuery && activeQuery.trim().length > 0) {
        // No server cache to clear for arbitrary queries; just refetch
        fetchTweets();
      } else {
        await refreshTopicTweets(topicSlug);
        const data = await fetchTweets();
        if (data && data.length >= 1) {
          setSummaryLoading(true);
          setSummaryError(null);
          setSummary(null);
          try {
            const s = await getTopicTweetsSummary(topicSlug, 10);
            const bullets = s?.bullets || [];
            const limited = data.length <= 3 ? bullets.slice(0, 1) : bullets.slice(0, 3);
            setSummary(limited);
          } catch (e: any) {
            setSummaryError(typeof e?.message === "string" ? e.message : "");
          } finally {
            setSummaryLoading(false);
          }
        } else {
          // 0 tweets: no summary
          setSummary(null);
          setSummaryError(null);
          setSummaryLoading(false);
        }
      }
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Failed to refresh");
    } finally {
      setRefreshing(false);
    }
  };

  const showSummarySection = !activeQuery && (summaryLoading || summaryError || (summary && summary.length > 0));

  return (
    <div className={`community-feed ${anim === "out" ? "cf-fade-out" : anim === "in" ? "cf-fade-in" : ""}`}>
      <div className="cf-header">
        <span className="cf-title">{activeQuery ? "Related X Tweets to Highlight" : "Top Tweets"}</span>
        <div className="cf-header-right">
          {activeQuery ? (
            onClearSearch ? (
              <button
                className="cf-refresh"
                onClick={onClearSearch}
                title="Back to Top Tweets"
                aria-label="Back to Top Tweets"
              >
                ←
              </button>
            ) : null
          ) : (
            <button
              className="cf-refresh"
              onClick={onRefresh}
              disabled={loading || refreshing}
              aria-label="Refresh: clears cache and fetches latest top tweets for this topic"
              title="Refresh the list: clears the server cache for this topic and fetches the latest top tweets. Use if results look stale or the topic changed."
            >
              ↻
            </button>
          )}
        </div>
      </div>
      {activeQuery && (
        <div className="cf-hints" onDoubleClick={startEdit}>
          {editingQuery ? (
            <input
              className="cf-hints-edit"
              value={draftQuery}
              onChange={(e) => setDraftQuery(e.target.value)}
              placeholder="Edit keywords and press Enter to search"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  const q = draftQuery.trim();
                  setEditingQuery(false);
                  if (q) beginQueryChange(q);
                } else if (e.key === 'Escape') {
                  setEditingQuery(false);
                }
              }}
              onBlur={() => setEditingQuery(false)}
            />
          ) : null}
          {(!editingQuery) && searchHints && (searchHints.keywords?.length > 0 || searchHints.topics?.length > 0) && (
            <>
              <div className="cf-hints-header">
                <span className="cf-hints-title">Search Keywords</span>
                <div className="cf-hints-actions">
                  <span className="cf-hints-tip">Double-click to edit</span>
                  <button
                    className="cf-hints-edit-btn"
                    type="button"
                    title="Edit keywords"
                    onClick={(e) => { e.stopPropagation(); startEdit(); }}
                  >
                    ✎ Edit
                  </button>
                </div>
              </div>
              {searchHints.keywords && searchHints.keywords.length > 0 && (
                <div className="cf-hints-row">
                  <span className="cf-hints-label">Searching for:</span>
                  <div className="cf-chips">
                    {searchHints.keywords.slice(0, 8).map((kw, i) => (
                      <span className="cf-chip" key={`kw-${i}`}>{kw}</span>
                    ))}
                  </div>
                </div>
              )}
              {searchHints.topics && searchHints.topics.length > 0 && (
                <div className="cf-hints-row">
                  <span className="cf-hints-label">Topics:</span>
                  <div className="cf-chips">
                    {searchHints.topics.slice(0, 5).map((tp, i) => (
                      <span className="cf-chip cf-chip-ghost" key={`tp-${i}`}>{tp}</span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
      {!activeQuery && showSummarySection && (
      <div className="cf-summary">
        {summaryLoading && <div className="cf-summary-loading">Summarizing…</div>}
        {!summaryLoading && summaryError && (
          <div className="cf-summary-error">Summary unavailable</div>
        )}
        {!summaryLoading && !summaryError && summary && summary.length > 0 && (
          <ul className="cf-summary-list">
            {summary.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        )}
      </div>
      )}
      {loading && <div className="cf-loading">Loading tweets…</div>}
      {error && (
        <div className="cf-error">
          {/* Common case: missing bearer token */}
          {error.includes("bearer token") ? (
            <span>Connect X API to see community feed.</span>
          ) : (
            <span>{error}</span>
          )}
        </div>
      )}
      {!loading && !error && tweets && tweets.length === 0 && (
        <div className="cf-empty">No related X tweets found.</div>
      )}
      <ul className="cf-list">
        {tweets?.map((t, idx) => (
          <li key={t.id} className="cf-item">
            <a href={t.url} target="_blank" rel="noopener noreferrer" className="cf-link">
              <div className="cf-item-row">
                <div className="cf-avatar-wrap">
                  {t.author_profile_image_url ? (
                    <img
                      src={t.author_profile_image_url}
                      alt={t.author_name || t.author_username}
                      className="cf-avatar"
                    />
                  ) : (
                    <div className="cf-avatar cf-avatar-fallback" />
                  )}
                  {!activeQuery && (
                    <div className={`cf-rank-badge ${idx < 3 ? `top${idx + 1}` : ""}`} aria-hidden>
                      {idx + 1}
                    </div>
                  )}
                </div>
                <div className="cf-meta">
                  <div className="cf-author">
                    <span className="cf-name">{t.author_name || t.author_username}</span>
                    {t.author_verified && (
                      <span className="cf-verified" title="Verified on X">✓</span>
                    )}
                    {t.author_name && (
                      <span className="cf-username">@{t.author_username}</span>
                    )}
                    {t.trending && !activeQuery && (
                      <span className="cf-trending" title="Recent and trending">Trending</span>
                    )}
                  </div>
                  <div className="cf-text" id={`cf-text-${t.id}`}>
                    {renderHighlightedText(t.text, String(t.id))}
                  </div>
                  {(t.like_count || t.retweet_count || t.reply_count || t.quote_count) && (
                    <div className="cf-stats">
                      {typeof t.like_count === "number" && <span>❤ {t.like_count}</span>}
                      {typeof t.retweet_count === "number" && <span>↻ {t.retweet_count}</span>}
                      {typeof t.reply_count === "number" && <span>💬 {t.reply_count}</span>}
                    </div>
                  )}
                </div>
              </div>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
