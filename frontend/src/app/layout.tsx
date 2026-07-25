import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Trading Arena",
  description: "Watch AI models compete as discretionary traders on real historical candlestick data.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full flex flex-col bg-[#06090F] text-[#E6EAF2]">{children}</body>
    </html>
  );
}
