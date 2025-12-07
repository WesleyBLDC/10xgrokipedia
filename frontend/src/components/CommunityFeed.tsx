import { useCallback, useEffect, useState } from "react";
import type { TweetItem } from "../api";
import { getTopicTweets, refreshTopicTweets } from "../api";

interface Props {
  topicSlug: string;
}

export default function CommunityFeed({ topicSlug }: Props) {
  const [tweets, setTweets] = useState<TweetItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const fetchTweets = useCallback(() => {
    setLoading(true);
    setError(null);
    setTweets(null);
    getTopicTweets(topicSlug, 10)
      .then(setTweets)
      .catch((e) => setError(typeof e?.message === "string" ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [topicSlug]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTweets(null);
    getTopicTweets(topicSlug, 10)
      .then((data) => {
        if (!cancelled) setTweets(data);
      })
      .catch((e) => {
        if (!cancelled) setError(typeof e?.message === "string" ? e.message : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [topicSlug]);

  // No explicit truncation hint; use CSS fade/clamp for a cleaner preview

  const onRefresh = async () => {
    try {
      setRefreshing(true);
      await refreshTopicTweets(topicSlug);
      fetchTweets();
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Failed to refresh");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="community-feed">
      <div className="cf-header">
        <span className="cf-title">Top Tweets</span>
        <div className="cf-header-right">
          <button
            className="cf-refresh"
            onClick={onRefresh}
            disabled={loading || refreshing}
            aria-label="Refresh: clears cache and fetches latest top tweets for this topic"
            title="Refresh the list: clears the server cache for this topic and fetches the latest top tweets. Use if results look stale or the topic changed."
          >
            ↻
          </button>
        </div>
      </div>
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
        <div className="cf-empty">No recent tweets found.</div>
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
                  <div className={`cf-rank-badge ${idx < 3 ? `top${idx + 1}` : ""}`} aria-hidden>
                    {idx + 1}
                  </div>
                </div>
                <div className="cf-meta">
                  <div className="cf-author">
                    <span className="cf-name">{t.author_name || t.author_username}</span>
                    {t.author_name && (
                      <span className="cf-username">@{t.author_username}</span>
                    )}
                  </div>
                  <div
                    className="cf-text"
                    id={`cf-text-${t.id}`}
                  >
                    {t.text}
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
