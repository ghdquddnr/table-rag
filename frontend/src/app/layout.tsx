import type { Metadata } from "next";
import { Inter, Noto_Sans_KR } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const notoSansKr = Noto_Sans_KR({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-noto-kr",
});

export const metadata: Metadata = {
  title: "table-rag | 표·숫자 특화 한국어 하이브리드 RAG",
  description: "Docling 파싱 + 표 인지 청킹 + pg_trgm word_similarity 하이브리드 검색(RRF) 기반의 한국어 표·숫자 특화 RAG 시스템 데모 대시보드",
};

export default function RootLayout({
  children,
  }: Readonly<{
    children: React.ReactNode;
  }>) {
  return (
    <html lang="ko" className={`${inter.variable} ${notoSansKr.variable}`}>
      <body>{children}</body>
    </html>
  );
}
