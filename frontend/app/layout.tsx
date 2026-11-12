import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import { Nav } from "@/components/nav";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ZCS LeadEngine",
  description: "Internal lead discovery tool",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Suspense: usePathname is dynamic on routes with params (/leads/[id]) under cacheComponents. */}
        <Suspense fallback={<div className="h-14 border-b" />}>
          <Nav />
        </Suspense>
        <main className="w-full flex-1 px-(--spacing-gutter) py-6">{children}</main>
      </body>
    </html>
  );
}
