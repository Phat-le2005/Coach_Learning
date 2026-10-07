import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/styles/tokens.css";
import "@/styles/motion.css";
import "@/styles/utilities.css";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "EduMS",
    template: "%s · EduMS",
  },
  description: "Không gian học tập thích ứng dành cho học sinh lớp 12.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
