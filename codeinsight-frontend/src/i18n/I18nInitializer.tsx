"use client";

import { useEffect, type ReactNode } from "react";
import i18n from "i18next";
import { I18nextProvider } from "react-i18next";
import { applyStoredLocale } from "./client";

/**
 * Client-side provider that:
 * 1. Restores the user's persisted locale preference on mount
 * 2. Wraps children with the i18n context
 *
 * i18n is initialized synchronously at module import time (client.ts),
 * so it's available immediately for SSR and first render.
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    applyStoredLocale();
  }, []);

  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}