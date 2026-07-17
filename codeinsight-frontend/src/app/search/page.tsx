"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { searchNodes, searchFiles, searchSuggestions } from "@/api/search";
import type { SearchNodeResult, SearchFileResult, SearchSuggestion } from "@/api/search";
import { cn } from "@/utils";

const SEARCH_TABS = ["代码节点", "文件"] as const;
type SearchTab = (typeof SEARCH_TABS)[number];

function getNodeTypeIcon(type: string): string {
  switch (type) {
    case "class": return "C";
    case "method": return "M";
    case "function": return "λ";
    case "interface": return "I";
    case "constructor": return "⚙";
    case "struct": return "S";
    case "enum": return "E";
    default: return "·";
  }
}

function getNodeTypeColor(type: string): string {
  switch (type) {
    case "class": return "bg-pink-100 text-pink-700";
    case "method": return "bg-purple-100 text-purple-700";
    case "function": return "bg-blue-100 text-blue-700";
    case "interface": return "bg-teal-100 text-teal-700";
    case "struct": return "bg-green-100 text-green-700";
    default: return "bg-gray-100 text-gray-700";
  }
}

export default function SearchPage() {
  const searchParams = typeof window !== "undefined"
    ? new URLSearchParams(window.location.search)
    : null;
  const repoIdFromUrl = searchParams?.get("repository_id") ?? null;

  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState<SearchTab>("代码节点");
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
      if (activeTab === "代码节点") {
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
    activeTab === "代码节点" && Array.isArray(r);

  return (
    <div className="max-w-4xl mx-auto py-6 px-4">
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
          placeholder="搜索代码中的类、函数、方法名..."
          className="w-full h-12 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 pl-12 text-base text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
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
          <div className="absolute z-10 top-full mt-1 w-full bg-[var(--bg-card)] border border-[var(--border)] rounded-lg shadow-lg overflow-hidden">
            {suggestions.map((s) => (
              <button
                key={s.text}
                className="w-full flex items-center gap-3 px-4 py-2 text-sm text-left hover:bg-[var(--bg-hover)] transition-colors"
                onMouseDown={() => handleSelectSuggestion(s.text)}
              >
                <span
                  className={cn(
                    "inline-flex items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-medium",
                    getNodeTypeColor(s.type)
                  )}
                >
                  {s.type}
                </span>
                <span className="text-[var(--text-primary)]">{s.text}</span>
                <span className="ml-auto text-[10px] text-[var(--text-muted)]">{s.count} 处</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-1 mb-4 border-b border-[var(--border)]">
        {SEARCH_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            {tab}
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
            {query ? "未找到匹配的代码节点" : "输入关键词开始搜索"}
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
                    getNodeTypeColor(node.nodeType)
                  )}
                >
                  {getNodeTypeIcon(node.nodeType)}
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
            {query ? "未找到匹配的文件" : "输入关键词开始搜索"}
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
                    {file.language} | {file.lineCount} 行
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        <div className="text-center text-sm text-[var(--text-muted)] py-12">
          输入关键词开始搜索
        </div>
      )}
    </div>
  );
}
