import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";

import { Sidebar } from "@/components/layout/Sidebar";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "RCM Intelligence · AI-powered Revenue Cycle Management",
  description: "Fine-tuned RCM SLM with RAG, deterministic analytics and validation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <div className="flex min-h-screen flex-col lg:flex-row">
          {/* Sidebar reads the pathname (URL data); on dynamic routes it streams in after the static shell. */}
          <Suspense fallback={<aside className="h-[57px] shrink-0 border-b border-line lg:h-screen lg:w-64 lg:border-r lg:border-b-0" />}>
            <Sidebar />
          </Suspense>
          <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
