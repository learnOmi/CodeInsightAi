"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "theme";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const shouldBeDark = stored === "dark" || (stored === null && prefersDark);
    document.documentElement.classList.toggle("dark", shouldBeDark);
    setDark(shouldBeDark);

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
      className="p-2 rounded-lg bg-[var(--bg-card)] border border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors"
      title={dark ? "切换亮色主题" : "切换暗色主题"}
    >
      {dark ? (
        <Sun className="w-5 h-5 text-yellow-400" />
      ) : (
        <Moon className="w-5 h-5 text-[var(--text-secondary)]" />
      )}
    </button>
  );
}
