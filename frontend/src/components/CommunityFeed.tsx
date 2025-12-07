import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  // Inline edit of whole query removed; we use chips instead
  const [addingKeyword, setAddingKeyword] = useState<boolean>(false);
  const [addDraft, setAddDraft] = useState<string>("");
  const [rawMode, setRawMode] = useState<boolean>(false);
  const [localKeywords, setLocalKeywords] = useState<string[] | null>(null);
  const [localTopics, setLocalTopics] = useState<string[] | null>(null);
  const skipNextFetchRef = useRef(false);
  const [hintsCollapsed, setHintsCollapsed] = useState<boolean>(false);
  const [searchingRelated, setSearchingRelated] = useState<boolean>(false);
  const thinking = (activeQuery ? (searchingRelated || refreshing) : (loading || summaryLoading));
  const inflightRef = useRef(false);

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

  const buildRawQuery = useCallback(() => {
    const kws = (localKeywords ?? searchHints?.keywords ?? []).map(s => s.trim()).filter(Boolean);
    const tps = (localTopics ?? searchHints?.topics ?? []).map(s => s.trim()).filter(Boolean);
    const all = Array.from(new Set([...kws, ...tps]));
    if (all.length === 0) return "";
    const norm = all.map(t => (t.includes(" ") ? `"${t}"` : t));
    return `(${norm.join(" OR ")})`;
  }, [localKeywords, localTopics, searchHints]);

  const fetchTweets = useCallback(async (opts?: { keepCurrent?: boolean }): Promise<TweetItem[] | null> => {
    const keepCurrent = !!opts?.keepCurrent;
    // Prevent duplicate concurrent calls in related mode
    const isRelated = !!(activeQuery && activeQuery.trim().length > 0);
    if (isRelated) {
      if (inflightRef.current) return null;
      inflightRef.current = true;
      setSearchingRelated(true);
    }
    if (!keepCurrent) {
      setLoading(true);
      setTweets(null);
    }
    setError(null);
    let data: TweetItem[] | null = null;
    try {
      if (activeQuery && activeQuery.trim().length > 0) {
        const res: SearchResult = await searchTweets(activeQuery, 10, { optimize: !rawMode, nocache: true });
        data = res?.tweets || [];
        setTweets(data);
        if (rawMode && (!res?.hints || (!res.hints.keywords?.length && !res.hints.topics?.length))) {
          const kws = localKeywords ?? searchHints?.keywords ?? [];
          const tps = localTopics ?? searchHints?.topics ?? [];
          setSearchHints({ query: activeQuery, keywords: kws, topics: tps });
        } else {
          setSearchHints(res?.hints || null);
        }
      } else {
        data = await getTopicTweets(topicSlug, 10);
        setTweets(data);
        setSearchHints(null);
        setRawMode(false);
        setLocalKeywords(null);
        setLocalTopics(null);
      }
      return data;
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Failed to load");
      setSearchHints(null);
      return null;
    } finally {
      if (isRelated) {
        setSearchingRelated(false);
        inflightRef.current = false;
      }
      if (!keepCurrent) setLoading(false);
    }
  }, [topicSlug, activeQuery, rawMode, localKeywords, localTopics, searchHints]);

  // Summary is now computed conditionally based on tweets count (see effects/onRefresh)

  useEffect(() => {
    let cancelled = false;
    setError(null);
    const run = async () => {
      try {
        if (activeQuery && activeQuery.trim().length > 0) {
          if (skipNextFetchRef.current) {
            // A manual refresh already triggered fetchTweets
            skipNextFetchRef.current = false;
          } else {
            await fetchTweets({ keepCurrent: !!tweets && tweets.length > 0 });
          }
          setSummary(null);
          setSummaryError(null);
          setSummaryLoading(false);
        } else {
          setLoading(true);
          setTweets(null);
          const data = await getTopicTweets(topicSlug, 10);
          if (!cancelled) setTweets(data);
          if (!cancelled) setSearchHints(null);
          if (!cancelled) {
            setRawMode(false);
            setLocalKeywords(null);
            setLocalTopics(null);
          }
          if (data && data.length >= 1) {
            setSummaryLoading(true);
            setSummaryError(null);
            setSummary(null);
            try {
              const s = await getTopicTweetsSummary(topicSlug, 10);
              const bullets = s?.bullets || [];
              const limited = data.length <= 3 ? bullets.slice(0, 1) : bullets.slice(0, 3);
              if (!cancelled) setSummary(limited);
            } catch (e: any) {
              if (!cancelled) setSummaryError(typeof e?.message === "string" ? e.message : "");
            } finally {
              if (!cancelled) setSummaryLoading(false);
            }
          } else {
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
    return () => { cancelled = true; };
  }, [topicSlug, activeQuery]);

  // No explicit truncation hint; use CSS fade/clamp for a cleaner preview

  const onRefresh = async () => {
    try {
      setRefreshing(true);
      if (activeQuery && activeQuery.trim().length > 0) {
        const hasEdits = (localKeywords !== null) || (localTopics !== null);
        if (hasEdits) {
          const nextQ = buildRawQuery();
          if (nextQ) {
            setRawMode(true);
            // Commit query and let the effect + fetchTweets handle the refresh in one path
            setActiveQuery(nextQ);
            setAddingKeyword(false);
          }
        } else {
          await fetchTweets({ keepCurrent: true });
        }
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
        <div className="cf-hints">
          <div className="cf-hints-header">
            <span className="cf-hints-title">Search Keywords</span>
            <div className="cf-hints-actions">
              <button
                className="cf-collapse-btn"
                type="button"
                title={hintsCollapsed ? "Expand keywords" : "Collapse keywords"}
                aria-label={hintsCollapsed ? "Expand keywords" : "Collapse keywords"}
                onClick={(e) => { e.stopPropagation(); setHintsCollapsed(!hintsCollapsed); }}
              >
                {hintsCollapsed ? "▸" : "▾"}
              </button>
              <button
                className="cf-hints-edit-btn"
                type="button"
                title="Refresh related tweets with current keywords"
                onClick={(e) => { e.stopPropagation(); onRefresh(); }}
              >
                ↻ Refresh
              </button>
              {refreshing && <span className="cf-spinner" aria-label="Refreshing" />}
            </div>
          </div>
          {!hintsCollapsed && (
          <div className="cf-hints-row" title="Hover to remove keywords; click + Add to add a keyword">
            <span className="cf-hints-label">Searching for:</span>
            <div className="cf-chips">
              {(localKeywords ?? searchHints?.keywords ?? []).slice(0, 20).map((kw, i) => (
                <span className="cf-chip cf-chip-removable" key={`kw-${i}`}>
                  {kw}
                  <button
                    type="button"
                    className="cf-chip-remove"
                    aria-label={`Remove ${kw}`}
                    title="Remove keyword"
                    onClick={(e) => {
                      e.stopPropagation();
                      const cur = [...(localKeywords ?? searchHints?.keywords ?? [])];
                      cur.splice(i, 1);
                      setLocalKeywords(cur);
                      setRawMode(true);
                      // pending: apply on Refresh
                    }}
                  >×</button>
                </span>
              ))}
              <button
                type="button"
                className={`cf-chip cf-chip-add ${addingKeyword ? "active" : ""}`}
                title="Add keyword"
                onClick={(e) => { e.stopPropagation(); setAddingKeyword(true); setAddDraft(""); }}
              >
                + Add
              </button>
            </div>
          </div>
          )}
          {!hintsCollapsed && thinking && (
            <div className="cf-hints-row cf-dots-row">
              <span className="cf-hints-label" />
              <span className="cf-dots" aria-live="polite" aria-label="Searching">
                <span>Searching</span>
                <span className="dot dot1"></span>
                <span className="dot dot2"></span>
                <span className="dot dot3"></span>
              </span>
            </div>
          )}
          {!hintsCollapsed && addingKeyword && (
            <div className="cf-hints-row">
              <span className="cf-hints-label" />
              <input
                className="cf-hints-edit"
                placeholder="Add a keyword and press Enter"
                value={addDraft}
                autoFocus
                onChange={(e) => setAddDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const val = addDraft.trim();
                    setAddingKeyword(false);
                    if (val) {
                      const cur = [...(localKeywords ?? searchHints?.keywords ?? [])];
                      if (!cur.includes(val)) cur.push(val);
                      setLocalKeywords(cur);
                      setRawMode(true);
                      // pending: applied on Refresh
                    }
                  } else if (e.key === 'Escape') {
                    setAddingKeyword(false);
                  }
                }}
                onBlur={() => setAddingKeyword(false)}
              />
            </div>
          )}
          {!hintsCollapsed && (localTopics ?? searchHints?.topics ?? []).length > 0 && (
            <div className="cf-hints-row topics">
              <span className="cf-hints-label">Topics:</span>
              <div className="cf-chips">
                {(localTopics ?? searchHints?.topics ?? []).slice(0, 10).map((tp, i) => (
                  <span className="cf-chip cf-chip-removable cf-chip-ghost" key={`tp-${i}`}>
                    {tp}
                    <button
                      type="button"
                      className="cf-chip-remove"
                      aria-label={`Remove ${tp}`}
                      title="Remove topic"
                      onClick={(e) => {
                        e.stopPropagation();
                        const cur = [...(localTopics ?? searchHints?.topics ?? [])];
                        cur.splice(i, 1);
                        setLocalTopics(cur);
                        setRawMode(true);
                        // pending: apply on Refresh
                      }}
                    >×</button>
                  </span>
                ))}
              </div>
            </div>
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
      {thinking && <div className="cf-thinking-bar" />}
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
