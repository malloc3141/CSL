import { Suspense, type ReactNode } from "react";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import { Providers } from "@/lib/providers";
import { I18nProvider } from "@/i18n";
import { defaultLocale } from "@/i18n/config";
import { getUserLocale } from "@/i18n/locale";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "CSL",
  description: "Classroom Simulation for Learning",
};

async function LocalizedContent({ children }: { children: ReactNode }) {
  const locale = await getUserLocale();
  return <I18nProvider locale={locale}>{children}</I18nProvider>;
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang={defaultLocale} className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <Providers>
          <Suspense fallback={null}>
            <LocalizedContent>{children}</LocalizedContent>
          </Suspense>
        </Providers>
      </body>
    </html>
  );
}
