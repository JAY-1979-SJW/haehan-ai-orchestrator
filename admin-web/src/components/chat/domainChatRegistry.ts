import type { ComponentType } from "react";

/**
 * 도메인별 전용 채팅 패널 등록부 — 공용 AI 패널(AiDock)이 기능 화면(app/…)을 직접 import 하지 않게,
 * 전용 패널을 가진 화면이 자기 모듈에서 등록한다(components → app 역방향 의존 제거).
 */
const panels = new Map<string, ComponentType>();
const listeners = new Set<() => void>();
let version = 0;

export function registerDomainChat(domain: string, panel: ComponentType): void {
  if (panels.get(domain) === panel) return;
  panels.set(domain, panel);
  version += 1;
  listeners.forEach((l) => l());
}

export function subscribeDomainChat(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function domainChatVersion(): number {
  return version;
}

export function getDomainChat(domain: string): ComponentType | undefined {
  return panels.get(domain);
}
