"use client";

import { useEffect, useState, useRef } from "react";
import { Moon, Sun } from "lucide-react";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";

const STORAGE_KEY = "theme";

export function ThemeToggle({ className }: { className?: string }) {
  const { t } = useTranslation();
  const [dark, setDark] = useState(false);
  const initializedRef = useRef(false);

  // Initialize theme on mount (page load), then update state based on DOM class
  useEffect(() => {
    if (initializedRef.current) return;

    const stored = localStorage.getItem(STORAGE_KEY);
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const shouldBeDark = stored === "dark" || (stored === null && prefersDark);

    // Apply initial theme if not already set
    const hasDarkClass = document.documentElement.classList.contains("dark");
    if (hasDarkClass !== shouldBeDark) {
      document.documentElement.classList.toggle("dark", shouldBeDark);
    }

    setDark(shouldBeDark);
    initializedRef.current = true;

    // Subscribe to subsequent theme changes via MutationObserver
    const observer = new MutationObserver(() => {
      setDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
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
      title={dark ? t("theme.darkLabel") : t("theme.lightLabel")}
    >
      <div className="flex items-center gap-2">
        <motion.div animate={{ rotate: dark ? 180 : 0 }} transition={{ duration: 0.3, ease: "easeInOut" }}>
          {dark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-[var(--text-secondary)]" />}
        </motion.div>
        <span className="text-xs font-medium text-[var(--text-primary)]">{dark ? t("theme.darkLabel") : t("theme.lightLabel")}</span>
      </div>
      <span className="text-xs text-[var(--text-muted)] group-hover:text-brand transition-colors">{dark ? "🌙" : "☀️"}</span>
    </button>
  );
}

// Version without theme initialization - safe for use in drawer that re-renders on open
export function ThemeToggleSafeForDrawer({ className }: { className?: string }) {
  const { t } = useTranslation();
  const [dark, setDark] = useState(false);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    setDark(document.documentElement.classList.contains("dark"));
    initializedRef.current = true;

    const observer = new MutationObserver(() => {
      setDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
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
      title={dark ? t("theme.darkLabel") : t("theme.lightLabel")}
    >
      <div className="flex items-center gap-2">
        <motion.div animate={{ rotate: dark ? 180 : 0 }} transition={{ duration: 0.3, ease: "easeInOut" }}>
          {dark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-[var(--text-secondary)]" />}
        </motion.div>
        <span className="text-xs font-medium text-[var(--text-primary)]">{dark ? t("theme.darkLabel") : t("theme.lightLabel")}</span>
      </div>
      <span className="text-xs text-[var(--text-muted)] group-hover:text-brand transition-colors">{dark ? "🌙" : "☀️"}</span>
    </button>
  );
}
