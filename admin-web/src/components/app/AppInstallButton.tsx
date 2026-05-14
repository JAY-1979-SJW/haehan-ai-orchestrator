"use client";

import { useEffect, useState } from "react";
import { Btn } from "@/components/ui";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

interface StandaloneNavigator extends Navigator {
  standalone?: boolean;
}

export function AppInstallButton() {
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(display-mode: standalone)");
    setInstalled(media.matches || (window.navigator as StandaloneNavigator).standalone === true);

    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };

    const onInstalled = () => {
      setInstalled(true);
      setInstallPrompt(null);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onInstalled);

    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const install = async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    await installPrompt.userChoice;
    setInstallPrompt(null);
  };

  if (installed) {
    return (
      <span className="inline-flex items-center rounded-md border border-[#BBF7D0] bg-[#ECFDF5] px-3 py-[7px] text-[12px] font-semibold text-[#047857]">
        앱으로 실행 중
      </span>
    );
  }

  return (
    <Btn
      variant="orange"
      onClick={install}
      disabled={!installPrompt}
      title={installPrompt ? "현재 기기에 앱으로 설치" : "브라우저 설치 조건이 준비되면 활성화됩니다"}
    >
      앱 설치
    </Btn>
  );
}
