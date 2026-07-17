"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";

export type NavTabType =
  | "overview"
  | "structure"
  | "callgraph"
  | "versions"
  | "routes"
  | "dependencies"
  | "frameworks"
  | "module-deps";

export interface NavEntry {
  component: NavTabType;
  fileId?: string | null;
  nodeId?: string | null;
  label: string;
  detail?: string;
}

export interface NavigableProps {
  onNavigate?: (entry: Omit<NavEntry, "component"> & { component?: NavTabType }) => void;
}

export function NavTrailBar({
  stack,
  onBack,
  onClear,
  onJumpTo,
}: {
  stack: NavEntry[];
  onBack: () => void;
  onClear: () => void;
  onJumpTo: (index: number) => void;
}) {
  const [isVisible, setIsVisible] = useState(true);
  const [position, setPosition] = useState({ x: 0, y: 200 });
  const [isDragging, setIsDragging] = useState(false);
  const dragOffset = useRef({ x: 0, y: 0 });
  const panelRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.target === panelRef.current || (e.target as HTMLElement).closest(".nav-panel-header")) {
      setIsDragging(true);
      dragOffset.current = {
        x: e.clientX - position.x,
        y: e.clientY - position.y,
      };
    }
  }, [position]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging) return;
    const container = document.querySelector(".nav-container");
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const maxX = rect.width - 240;
    const maxY = rect.height - 300;
    const newX = Math.max(0, Math.min(maxX, e.clientX - dragOffset.current.x - rect.left));
    const newY = Math.max(0, Math.min(maxY, e.clientY - dragOffset.current.y - rect.top));
    setPosition({ x: newX, y: newY });
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
      return () => {
        window.removeEventListener("mousemove", handleMouseMove);
        window.removeEventListener("mouseup", handleMouseUp);
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  if (stack.length === 0) return null;

  const toggleVisibility = () => {
    setIsVisible(!isVisible);
  };

  return (
    <>
      <button
        onClick={toggleVisibility}
        className={`fixed right-3 top-1/2 -translate-y-1/2 z-40 flex items-center justify-center w-8 h-16 rounded-l-lg transition-all duration-300 ${
          isVisible
            ? "bg-[var(--bg-card)] border border-r-0 border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:w-10"
            : "bg-[var(--bg-card)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:w-10"
        }`}
        title={isVisible ? "隐藏导航面板" : "显示导航面板"}
      >
        <span className="text-lg">{isVisible ? "◀" : "▶"}</span>
      </button>

      <div
        ref={panelRef}
        className={`fixed z-50 w-[230px] bg-[var(--bg-card)] border border-[var(--border)] rounded-lg shadow-xl overflow-hidden transition-all duration-300 ${
          isVisible ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none translate-x-full"
        }`}
        style={{
          right: "35px",
          top: `${position.y}px`,
          maxHeight: "calc(100vh - 200px)",
        }}
        onMouseDown={handleMouseDown}
      >
        <div className="nav-panel-header flex items-center justify-between px-3 py-2 border-b border-[var(--border)] bg-[var(--bg-hover)] cursor-move">
          <span className="text-xs font-medium text-[var(--text-primary)]">探索轨迹</span>
          <div className="flex items-center gap-1">
            <button
              onClick={onBack}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] px-1.5 py-0.5 rounded hover:bg-[var(--bg-card)] transition-colors"
              title="返回上一步"
            >
              ← 返回
            </button>
            <button
              onClick={onClear}
              className="text-xs text-[var(--text-muted)] hover:text-red-400 px-1.5 py-0.5 rounded hover:bg-[var(--bg-card)] transition-colors"
              title="清空轨迹"
            >
              ×
            </button>
          </div>
        </div>

        <div className="overflow-y-auto max-h-[400px]">
          {stack.map((entry, index) => (
            <React.Fragment key={`${entry.component}-${index}-${entry.label}`}>
              <button
                onClick={() => onJumpTo(index)}
                className={`w-full text-left px-3 py-2 text-xs transition-colors flex items-center gap-2 ${
                  index === stack.length - 1
                    ? "bg-blue-50/50 text-[var(--text-primary)] font-medium"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
                }`}
                title={`${entry.label} - ${entry.detail || ""}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  index === stack.length - 1 ? "bg-blue-500" : "bg-[var(--text-muted)]"
                }`} />
                <span className="truncate">{entry.label}</span>
                {entry.detail && (
                  <span className="text-[var(--text-muted)] flex-shrink-0">({entry.detail})</span>
                )}
              </button>
              {index < stack.length - 1 && (
                <div className="h-px bg-[var(--border)] mx-4" />
              )}
            </React.Fragment>
          ))}
        </div>

        <div className="px-3 py-2 border-t border-[var(--border)] bg-[var(--bg-hover)]">
          <span className="text-[10px] text-[var(--text-muted)]">
            {stack.length} 步 · 点击拖拽移动面板
          </span>
        </div>
      </div>
    </>
  );
}
