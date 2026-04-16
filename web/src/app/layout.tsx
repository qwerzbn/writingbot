import type { Metadata } from "next";
import "./globals.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import AppFrame from "@/components/AppFrame";
import { AppProvider } from "@/context/AppContext";

export const metadata: Metadata = {
  title: "WritingBot - 智能知识库",
  description: "Multi-Knowledge Base RAG System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="antialiased">
        <AppProvider>
          <AppFrame>{children}</AppFrame>
        </AppProvider>
      </body>
    </html>
  );
}
