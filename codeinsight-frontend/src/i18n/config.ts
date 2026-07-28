import i18n from "i18next";
import { initReactI18next } from "react-i18next";

/** Shared UI translation namespace */
export const NS = "translation" as const;

/** Available locales in this app */
export const LOCALES = {
  "zh-CN": "中文",
  "en-US": "English",
} as const;

/** Default locale */
export const DEFAULT_LOCALE = "zh-CN" as const;

/** Storage key for persisted locale */
export const LOCALE_STORAGE_KEY = "codeinsight_locale";

/**
 * Initialize i18next with bundled resources (no network calls).
 * Resources are inlined via `import` so they ship in the build bundle.
 */
export async function initI18n(): Promise<typeof i18n> {
  await i18n.use(initReactI18next).init({
    resources: {},
    fallbackLng: DEFAULT_LOCALE,
    defaultNS: NS,
    interpolation: {
      escapeValue: false, // React already escapes
    },
    react: {
      useSuspense: false, // Next.js 15 app router — avoid suspense in SSR
    },
    // Suppress missing-key warnings during development to keep console clean
    // until all translation strings are wired up
    missingKeyHandler: (lng, ns, key) => {
      if (process.env.NODE_ENV === "development") {
        console.warn("[i18n] Missing key:", lng, ns, key);
      }
    },
  });
  return i18n;
}
