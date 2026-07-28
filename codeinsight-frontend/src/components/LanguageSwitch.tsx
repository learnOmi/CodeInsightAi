"use client";

import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";
import { setLocale } from "@/i18n/client";
import { LOCALES, DEFAULT_LOCALE } from "@/i18n/config";

/**
 * Language switcher — toggles between configured locales
 * and persists the choice to localStorage.
 */
export function LanguageSwitch() {
  const { i18n } = useTranslation();
  const current = i18n.language ?? DEFAULT_LOCALE;

  const toggle = () => {
    const next = current === "zh-CN" ? "en-US" : "zh-CN";
    setLocale(next);
  };

  return (
    <button
      onClick={toggle}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white/[0.04] transition-all duration-300 ease-out whitespace-nowrap active:scale-95"
      title="Toggle language"
    >
      <Globe className="w-3.5 h-3.5" />
      <span className="font-semibold text-[var(--text-primary)]">{LOCALES[current as keyof typeof LOCALES] ?? current}</span>
    </button>
  );
}
