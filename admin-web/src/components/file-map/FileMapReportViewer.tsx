'use client';

import { useState, useEffect } from 'react';
import {
  loadSettings,
  saveSettings,
  shouldRevealSensitiveNames,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';
import { ReportHeader } from './report/ReportHeader';
import { ReportContent } from './report/ReportContent';
import { ReportPolicyNotice } from './report/ReportPolicyNotice';
import { ReportMaskingSettings } from './report/ReportMaskingSettings';

interface RevealSessionState {
  auth_verified: boolean;
  reveal_sensitive_names: boolean;
  expires_at: number | null;
}

interface FileObject {
  name: string;
  path: string;
  size: number;
  [key: string]: any;
}

export interface FileMapReportViewerProps {
  reportData?: {
    title: string;
    content: string;
    files: FileObject[];
    [key: string]: any;
  };
  revealData?: {
    title?: string;
    content?: string;
    files?: FileObject[];
    [key: string]: any;
  };
}

export function FileMapReportViewer({
  reportData,
  revealData
}: FileMapReportViewerProps) {
  const [session, setSession] = useState<RevealSessionState>({
    auth_verified: false,
    reveal_sensitive_names: false,
    expires_at: null,
  });

  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const [revealReportData, setRevealReportData] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);

  // 설정 로드
  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
  }, []);

  // 시간 남은 것 업데이트
  useEffect(() => {
    if (!session.auth_verified || !session.expires_at) {
      setTimeRemaining(null);
      return;
    }

    const updateTimer = () => {
      const now = Date.now();
      const remaining = Math.max(0, (session.expires_at ?? 0) - now);
      setTimeRemaining(remaining);

      if (remaining === 0) {
        handleRemask();
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [session.auth_verified, session.expires_at]);

  const handleMockAuth = async () => {
    try {
      setIsAuthLoading(true);
      const response = await fetch('/api/file-map/auth/mock-verify', {
        method: 'POST',
      });
      const data = await response.json();

      if (data.ok) {
        setSession({
          auth_verified: true,
          reveal_sensitive_names: true,
          expires_at: new Date(data.expires_at).getTime(),
        });
      }
    } catch (error) {
      console.error('Auth failed:', error);
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleRevealToggle = async () => {
    if (!settings) return;

    switch (settings.maskingMode) {
      case 'mask_always':
        return;

      case 'reveal_after_auth': {
        if (!session.auth_verified) {
          return;
        }
        if (session.reveal_sensitive_names) {
          setSession((prev) => ({
            ...prev,
            reveal_sensitive_names: false,
          }));
          return;
        }
        try {
          const response = await fetch('/api/file-map/report?mode=reveal_after_auth');
          const data = await response.json();
          if (data.ok && data.report) {
            setRevealReportData(data.report);
            setSession((prev) => ({
              ...prev,
              reveal_sensitive_names: true,
            }));
          }
        } catch (error) {
          console.error('Reveal error:', error);
        }
        break;
      }

      case 'reveal_on_trusted_device': {
        setSession((prev) => ({
          ...prev,
          reveal_sensitive_names: !prev.reveal_sensitive_names,
        }));
        break;
      }

      case 'reveal_for_export_with_warning':
        break;
    }
  };

  const handleSaveSetting = (mode: FileMapMaskingMode) => {
    const newSettings = { ...settings, maskingMode: mode };
    setSettings(newSettings);
    saveSettings(newSettings);
  };

  const handleRemask = async () => {
    try {
      await fetch('/api/file-map/auth/clear', {
        method: 'POST',
      });
    } catch (error) {
      console.error('Clear failed:', error);
    }

    setSession({
      auth_verified: false,
      reveal_sensitive_names: false,
      expires_at: null,
    });
  };

  const isMasked = settings
    ? !shouldRevealSensitiveNames(settings.maskingMode, session.auth_verified)
    : true;

  return (
    <div className="file-map-report-viewer p-4 border rounded-lg bg-white">
      <ReportHeader
        isMasked={isMasked}
        isAuthVerified={session.auth_verified}
        timeRemaining={timeRemaining}
        isAuthLoading={isAuthLoading}
        onRevealToggle={handleRevealToggle}
        onRemask={handleRemask}
        onMockAuth={handleMockAuth}
      />

      <hr className="my-4" />

      <ReportContent
        reportData={reportData}
        revealReportData={revealReportData}
        isRevealing={session.reveal_sensitive_names}
      />

      <ReportPolicyNotice />

      <ReportMaskingSettings
        settings={settings}
        onSaveSetting={handleSaveSetting}
      />
    </div>
  );
}
