import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/styles/tokens.css";
import "@/styles/motion.css";
import "@/styles/utilities.css";
import "katex/dist/katex.min.css";
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
    <html lang="vi" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                var origError = console.error;
                console.error = function() {
                  var first = arguments[0];
                  if (typeof first === "string" && first.indexOf("onnxruntime") !== -1 && first.indexOf("Unknown CPU vendor") !== -1) {
                    console.warn.apply(console, arguments);
                    return;
                  }
                  origError.apply(console, arguments);
                };
              })();
            `,
          }}
        />
      </head>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
