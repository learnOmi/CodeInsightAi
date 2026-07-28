"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { searchNodes, searchFiles, searchSuggestions } from "@/api/search";
import type { SearchNodeResult, SearchFileResult, SearchSuggestion } from "@/api/search";
import { cn } from "@/utils";
import { GlobalNav } from "@/components/GlobalNav";
import { useTranslation } from "react-i18next";

const SEARCH_TABS = ["nodes", "files"] as const;
type SearchTab = (typeof SEARCH_TABS)[number];

export default function SearchPage() {
  const { t } = useTranslation();
  const searchParams = typeof window !== "undefined"
    ? new URLSearchParams(window.location.search)
    : null;
  const repoIdFromUrl = searchParams?.get("repository_id") ?? null;

  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState<SearchTab>("nodes");
  const [results, setResults] = useState<SearchNodeResult[] | SearchFileResult[] | null>(null);
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const inputRef = useRef<HTMLInputElement>(null);
  const queryRef = useRef(query);
  queryRef.current = query;

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults(null);
      return;
    }
    setLoading(true);
    try {
      if (activeTab === "nodes") {
        const res = await searchNodes({
          q: q.trim(),
          repository_id: repoIdFromUrl ?? undefined,
          limit: 30,
        });
        setResults(res);
      } else {
        const res = await searchFiles({
          q: q.trim(),
          repository_id: repoIdFromUrl ?? undefined,
          limit: 20,
        });
        setResults(res);
      }
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab, repoIdFromUrl]);

  const fetchSuggestions = useCallback(async (q: string) => {
    if (!q.trim() || q.trim().length < 1) {
      setSuggestions([]);
      return;
    }
    try {
      const res = await searchSuggestions(q.trim(), repoIdFromUrl ?? undefined, 8);
      setSuggestions(res.suggestions);
    } catch {
      setSuggestions([]);
    }
  }, [repoIdFromUrl]);

  const handleInputChange = (value: string) => {
    setQuery(value);
    setShowSuggestions(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchSuggestions(value);
    }, 200);
  };

  const handleSelectSuggestion = (text: string) => {
    setQuery(text);
    setShowSuggestions(false);
    doSearch(text);
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      setShowSuggestions(false);
      doSearch(query);
    }
  };

  // 当 activeTab 切换时，如果已有 query 则重新搜索
  useEffect(() => {
    const q = queryRef.current;
    if (q.trim()) {
      doSearch(q);
    }
  }, [activeTab, doSearch]);

  const isNodeResults = (r: typeof results): r is SearchNodeResult[] =>
    activeTab === "nodes" && Array.isArray(r);

  return (
    <div className="max-w-4xl mx-auto py-6 px-4">
      <GlobalNav />
      <div className="mt-4">
        <header className="mb-8 relative">
          {/* 标题后方光晕 */}
          <div className="absolute -top-8 -left-8 w-48 h-48 rounded-full bg-brand/10 blur-[100px] pointer-events-none" />
          <h1 className="text-5xl font-bold tracking-tight relative">
            <span className="bg-gradient-to-r from-brand via-brand-fg to-status-info bg-clip-text text-transparent">
              {t("search.title")}
            </span>
          </h1>
          <p className="mt-2 text-base text-[var(--text-muted)] tracking-wide">
            {t("search.subtitle")}
          </p>
        </header>

        {/* 搜索框 */}
        <div className="relative mb-6">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleInputChange(e.target.value)}
            onFocus={() => setShowSuggestions(true)}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
            onKeyDown={handleKeyDown}
            placeholder={t("search.placeholder")}
            className="w-full h-12 rounded-xl border border-white/[0.06] bg-[var(--bg-card)]/70 backdrop-blur-xl px-4 pl-12 text-base text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-brand/40 focus:ring-2 focus:ring-brand/20 focus:shadow-[var(--glow-brand-light)] transition-all"
          />
          <svg
            className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text-muted)]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>

          {/* 建议下拉 */}
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute z-10 top-full mt-1 w-full bg-[var(--bg-card)] border border-white/[0.06] rounded-xl shadow-2xl overflow-hidden backdrop-blur-xl">
              {suggestions.map((s) => (
                <button
                  key={s.text}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-left hover:bg-[var(--bg-hover)] transition-colors"
                  onMouseDown={() => handleSelectSuggestion(s.text)}
                >
                  <span
                    className={cn(
                      "inline-flex items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-medium",
                      s.type === "class" ? "bg-pink-100 text-pink-700" :
                      s.type === "method" ? "bg-purple-100 text-purple-700" :
                      s.type === "function" ? "bg-blue-100 text-blue-700" :
                      s.type === "interface" ? "bg-teal-100 text-teal-700" :
                      s.type === "struct" ? "bg-green-100 text-green-700" :
                      "bg-gray-100 text-gray-700"
                    )}
                  >
                    {s.type}
                  </span>
                  <span className="text-[var(--text-primary)]">{s.text}</span>
                  <span className="ml-auto text-[10px] text-[var(--text-muted)">{`${s.count} ${t('search.occurrences')}`}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Tab 切换 — 品牌色 */}
        <div className="flex gap-1 mb-4 border-b border-[var(--border)]">
          {SEARCH_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? "border-brand text-brand"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              {t(`search.tabs.${tab}`)}
            </button>
          ))}
        </div>

        {/* 搜索结果 */}
        {loading ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-[var(--bg-hover)] rounded-lg animate-pulse" />
            ))}
          </div>
        ) : isNodeResults(results) ? (
          results.length === 0 ? (
            <div className="text-center text-sm text-[var(--text-muted)] py-12">
              {query ? t("search.emptyNodes") : t("search.emptyInput")}
            </div>
          ) : (
            <div className="space-y-1">
              {results.map((node) => (
                <div
                  key={node.id}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-[var(--bg-hover)] transition-colors"
                >
                  <span
                    className={cn(
                      "inline-flex items-center justify-center w-6 h-6 rounded text-xs font-bold flex-shrink-0",
                      node.nodeType === "class" ? "bg-pink-100 text-pink-700" :
                      node.nodeType === "method" ? "bg-purple-100 text-purple-700" :
                      node.nodeType === "function" ? "bg-blue-100 text-blue-700" :
                      node.nodeType === "interface" ? "bg-teal-100 text-teal-700" :
                      node.nodeType === "struct" ? "bg-green-100 text-green-700" :
                      "bg-gray-100 text-gray-700"
                    )}
                  >
                    {node.nodeType === "class" ? "C" :
                     node.nodeType === "method" ? "M" :
                     node.nodeType === "function" ? "λ" :
                     node.nodeType === "interface" ? "I" :
                     node.nodeType === "constructor" ? "⚙" :
                     node.nodeType === "struct" ? "S" :
                     node.nodeType === "enum" ? "E" : "·"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-[var(--text-primary)] truncate">
                        {node.name}
                      </span>
                      {node.tags && node.tags.length > 0 && (
                        <span className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-medium bg-blue-100 text-blue-700">
                          {node.tags[0]}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-[var(--text-muted)] truncate font-mono">
                      {node.filePath}:{node.startLine}-{node.endLine}
                      {node.qualifiedName && ` | ${node.qualifiedName}`}
                    </div>
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)] flex-shrink-0">{node.language}</span>
                </div>
              ))}
            </div>
          )
        ) : Array.isArray(results) ? (
          (results as SearchFileResult[]).length === 0 ? (
            <div className="text-center text-sm text-[var(--text-muted)] py-12">
              {query ? t("search.emptyFiles") : t("search.emptyInput")}
            </div>
          ) : (
            <div className="space-y-1">
              {(results as SearchFileResult[]).map((file) => (
                <div
                  key={file.id}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-[var(--bg-hover)] transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-mono text-[var(--text-primary)] truncate">
                      {file.path}
                    </div>
                    <div className="text-xs text-[var(--text-muted)]">
                      {file.language} | {file.lineCount} {t('search.lines')}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )
        ) : (
          <div className="text-center text-sm text-[var(--text-muted)] py-12">
            {t("search.emptyInput")}
          </div>
        )}
      </div>
    </div>
  );
}