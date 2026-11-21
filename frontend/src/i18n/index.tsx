"use client";

import { createContext, useContext, useEffect, type ReactNode } from "react";
import { defaultLocale, type Locale } from "./config";
import { setUserLocale } from "./locale";
import en from "./en.json";
import ko from "./ko.json";

type MessageKey = keyof typeof en;
const messages = { en, ko } satisfies Record<Locale, Record<MessageKey, string>>;
const LocaleContext = createContext<Locale>(defaultLocale);

export function I18nProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useI18n() {
  const locale = useContext(LocaleContext);
  const t = (key: MessageKey, values?: Record<string, string | number>) =>
    messages[locale][key].replace(/\{(\w+)\}/g, (match, name: string) =>
      String(values?.[name] ?? match),
    );

  return { locale, t, setLocale: setUserLocale };
}
