"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html>
      <body>
        <div style={{ display: "flex", minHeight: "100dvh", alignItems: "center", justifyContent: "center", background: "#F5F7FA" }}>
          <div style={{ borderRadius: 16, border: "1px solid #FCA5A5", background: "#fff", padding: 32, maxWidth: 400, width: "100%", textAlign: "center" }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>⚠️</div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "#111827", marginBottom: 8 }}>앱 오류</h2>
            <p style={{ fontSize: 14, color: "#6B7280", marginBottom: 24 }}>{error.message || "예기치 않은 오류가 발생했습니다."}</p>
            <button
              onClick={reset}
              style={{ padding: "8px 20px", borderRadius: 8, background: "#F97316", color: "#fff", fontSize: 14, fontWeight: 600, border: "none", cursor: "pointer" }}
            >
              다시 시도
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
