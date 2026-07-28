"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useTranslation } from "react-i18next";
import { Sun, Moon, Globe } from "lucide-react";

const STORAGE_KEY = "theme";
const LOCALE_STORAGE_KEY = "codeinsight_locale";

// 主题切换按钮
function ThemeButton({ className }: { className?: string }) {
  const [dark, setDark] = useState(false);
  const { t } = useTranslation();

  // 仅在初始化时读取主题偏好，不监听 DOM 变化，防止点击触发器时误触发
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const shouldBeDark = stored === "dark" || (stored === null && prefersDark);
    document.documentElement.classList.toggle("dark", shouldBeDark);
    setDark(shouldBeDark);
  }, []);

  const toggle = () => {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    setDark(next);
  };

  return (
    <button
      onClick={toggle}
      className={`flex items-center justify-between px-3 py-2 text-left transition-colors hover:bg-[var(--bg-hover)] ${className || ""}`}
      tabIndex={0}
    >
      <div className="flex items-center gap-2">
        <motion.div animate={{ rotate: dark ? 180 : 0 }} transition={{ duration: 0.3, ease: "easeInOut" }}>
          {dark ? (
            <Sun className="w-4 h-4 text-amber-400" />
          ) : (
            <Moon className="w-4 h-4 text-[var(--text-secondary)]" />
          )}
        </motion.div>
        <span className="text-xs font-medium text-[var(--text-primary)]">{dark ? t("theme.darkLabel") : t("theme.lightLabel")}</span>
      </div>
      <span className="text-xs text-[var(--text-muted)] group-hover:text-brand transition-colors">{dark ? "🌙" : "☀️"}</span>
    </button>
  );
}

// 语言切换按钮
function LanguageButton({ className }: { className?: string }) {
  const { i18n } = useTranslation();
  const [current, setCurrent] = useState(i18n.language ?? "zh-CN");

  const toggle = () => {
    const next = current === "zh-CN" ? "en-US" : "zh-CN";
    localStorage.setItem(LOCALE_STORAGE_KEY, next);
    i18n.changeLanguage(next);
    setCurrent(next);
  };

  const LOCALES = { "zh-CN": "中文", "en-US": "English" };

  return (
    <button
      onClick={toggle}
      className={`flex items-center justify-between px-3 py-2 text-left transition-colors hover:bg-[var(--bg-hover)] ${className || ""}`}
      tabIndex={0}
    >
      <div className="flex items-center gap-2">
        <Globe className="w-4 h-4 text-[var(--text-muted)] group-hover:text-brand transition-colors" />
        <span className="text-xs font-medium text-[var(--text-primary)]">{LOCALES[current as keyof typeof LOCALES] ?? current}</span>
      </div>
      <span className="text-xs text-[var(--text-muted)] group-hover:text-brand transition-colors">⇄</span>
    </button>
  );
}

export function CombinedControlDrawer() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const timeoutRef = useRef<number | null>(null);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;

    const handleClick = (e: MouseEvent) => {
      if (buttonRef.current && containerRef.current && !(containerRef.current.contains(e.target as Node | null))) {
        setOpen(false);
      }
    };
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [open]);

  // 平滑展开时的焦点管理
  useEffect(() => {
    if (open) {
      timeoutRef.current = window.setTimeout(() => {
        const firstBtn = containerRef.current?.querySelector("button");
        (firstBtn as HTMLElement)?.focus();
      }, 100);
    }
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [open]);

  return (
    <div className="relative flex flex-col-reverse items-start">
      {/* 触发按钮 - 始终显示在左下角 */}
      <button
        ref={buttonRef}
        onClick={() => setOpen(!open)}
        className="w-10 h-10 rounded-full bg-[var(--bg-card)] border border-[var(--border)] shadow-lg hover:shadow-xl transition-all duration-200 flex items-center justify-center text-[var(--text-primary)] hover:text-brand hover:bg-brand/5 active:scale-95 z-60"
        title={open ? t("controls.close") : t("controls.open")}
      >
        <span className="text-lg">{open ? "✕" : "⚙️"}</span>
      </button>

      {/* 展开的 bar — 从按钮正上方垂直向上展开，宽度与触发按钮一致，圆角设计 */}
      <AnimatePresence mode="wait">
        {open && (
          <motion.div
            ref={containerRef}
            initial={{ opacity: 0, y: -12, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 300, damping: 20, duration: 0.3 }}
            className="absolute bottom-[-1px] left-0 w-10 origin-bottom rounded-t-lg border-b border-[var(--border)] bg-[var(--bg-card)] divide-y divide-[var(--border)] overflow-hidden shadow-md"
            style={{ zIndex: 59 }}
          >
            {/* 语言切换 - 第一个按钮 */}
            <div className="px-2 py-2">
              <LanguageButton className="w-full" />
            </div>

            {/* 主题设置 - 第二个按钮 */}
            <div className="px-2 py-2">
              <ThemeButton className="w-full" />
            </div>

            {/* 底部说明 */}
            <div className="px-2 py-1.5 bg-[var(--bg-hover)]/50 text-[9px] text-[var(--text-muted)] border-b border-[var(--border)]">
              {t("controls.footer")}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}