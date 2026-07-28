import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import zh from "@/i18n/resources/zh-CN";
import en from "@/i18n/resources/en-US";
import { DEFAULT_LOCALE, LOCALE_STORAGE_KEY, NS } from "./config";

/** Locale display names for the switcher */
export const LOCALES: Record<string, string> = {
  "zh-CN": "中文",
  "en-US": "English",
};

/**
 * Initialize i18n synchronously so it's available immediately
 * (including during SSR/static generation).
 */
const resources: Record<string, { translation: Record<string, unknown> }> = {
  "zh-CN": { translation: zh },
  "en-US": { translation: en },
};

i18n.use(initReactI18next).init({
  resources,
  lng: DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  defaultNS: NS,
  supportedLngs: ["zh-CN", "en-US"],
  interpolation: { escapeValue: false },
  react: { useSuspense: false },
  missingKeyHandler: (lng, ns, key) => {
    if (process.env.NODE_ENV === "development") {
      console.warn("[i18n] Missing key:", lng, ns, key);
    }
  },
});

/**
 * Read persisted locale preference, falling back to DEFAULT_LOCALE.
 * Only reads from localStorage on the client.
 */
export function getStoredLocale(): string {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (!stored) return DEFAULT_LOCALE;
  return ["zh-CN", "en-US"].includes(stored) ? stored : DEFAULT_LOCALE;
}

/**
 * Persist locale preference to localStorage and switch runtime language.
 * No-op on the server.
 */
export function setLocale(lng: string): void {
  if (typeof window === "undefined") return;
  const locale = ["zh-CN", "en-US"].includes(lng) ? lng : DEFAULT_LOCALE;
  localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  i18n.changeLanguage(locale);
}

/**
 * Apply the persisted locale on first client render.
 * Call this once in a useEffect to restore the user's preference.
 */
export function applyStoredLocale(): void {
  if (typeof window === "undefined") return;
  const stored = getStoredLocale();
  if (stored !== i18n.language) {
    i18n.changeLanguage(stored);
  }
}