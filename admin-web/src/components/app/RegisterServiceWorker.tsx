"use client";

import { useEffect } from "react";

export function RegisterServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    // SW 비활성화: 캐시-서빙 SW가 빌드 변경 시 stale 자원을 서빙해 화면이 깨지던
    // 문제를 막기 위해, 등록하지 않고 기존 SW를 모두 해제 + 캐시 삭제한다.
    navigator.serviceWorker
      .getRegistrations()
      .then((regs) => regs.forEach((r) => r.unregister()))
      .catch(() => {});
    if (typeof caches !== "undefined") {
      caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => {});
    }
  }, []);

  return null;
}
