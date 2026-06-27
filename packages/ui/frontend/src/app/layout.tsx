import type { Metadata } from "next";
import "./globals.css";
import { Suspense } from "react";
import { Sidebar } from "@/components/Sidebar";
import Providers from "@/components/Providers";

export const metadata: Metadata = {
  title: "MONITOR — Narrative AI",
  description: "Multi-Ontology Narrative Intelligence Through Omniversal Representation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full flex overflow-hidden dot-grid">
        <Providers>
          {/* Fixed sidebar. Wrapped in Suspense because Sidebar (via
              WorldPicker) calls useSearchParams() — without Suspense,
              Next 15 prerender bails on every page. The skeleton renders
              instantly; the live search-params content swaps in after
              hydration. */}
          <Suspense fallback={<div className="w-[224px] shrink-0" aria-hidden="true" />}>
            <Sidebar />
          </Suspense>
          {/* Main content */}
          <main className="flex-1 flex flex-col overflow-hidden relative">
            {/* Scan line decoration */}
            <div className="scan-line" />
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
