import type { Metadata } from "next";
import { Poppins } from "next/font/google";

import "./globals.css";

const bodyFont = Poppins({
  variable: "--font-body",
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "QualiAgent",
  description: "Analiza materiału jakościowego z cytatami zakotwiczonymi w źródłach",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pl" className={`${bodyFont.variable} h-full`}>
      <body className="min-h-full font-sans antialiased">{children}</body>
    </html>
  );
}
