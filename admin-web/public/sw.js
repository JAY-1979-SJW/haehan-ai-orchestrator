// 자기 제거 Service Worker — 캐시 간섭 제거.
// (이전 cache-first SW가 빌드 변경 시 stale 자원을 서빙해 화면이 깨지던 문제 해결.
//  이 앱은 항상 온라인이라 오프라인 캐시가 불필요하므로 SW를 비활성화한다.)
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k))); // 모든 캐시 삭제
      await self.registration.unregister(); // 자기 자신 등록 해제
      const clients = await self.clients.matchAll();
      clients.forEach((c) => c.navigate(c.url)); // 새로고침해 네트워크 직접 로드
    })()
  );
});
// fetch 핸들러 없음 → 요청 가로채지 않음 (항상 네트워크 직접)
