import fs from 'fs';
import path from 'path';
import { maskFileObject, maskPath } from '@/lib/privacy';

export type FileMapMaskingMode = 'mask_always' | 'reveal_after_auth' | 'reveal_on_trusted_device' | 'reveal_for_export_with_warning';

export interface FileMapReport {
  title?: string;
  scan_root?: string;
  scan_timestamp?: string;
  total_files?: number;
  categories?: Record<string, any>;
  large_files?: any[];
  old_files?: any[];
  suspicious_duplicates?: any[];
  suspicious_temp?: any[];
  recommendations?: string[];
  [key: string]: any;
}

export interface ApiResponse {
  ok: boolean;
  generated_at: string;
  source: string;
  masked: boolean;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  export_warning?: boolean;
  report?: FileMapReport;
  error?: string;
  storage_info?: any;
}

export function getStoragePath(): string {
  const home = process.env.USERPROFILE || process.env.HOME || '';
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory');
}

export function loadReport(storagePath: string): FileMapReport | null {
  const reportPath = path.join(storagePath, 'local_file_map.json');

  try {
    if (!fs.existsSync(reportPath)) {
      return null;
    }

    const content = fs.readFileSync(reportPath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    console.error('Failed to load report:', error);
    return null;
  }
}

export function maskReport(report: FileMapReport): FileMapReport {
  if (!report) return report;

  const masked = { ...report };

  if (masked.large_files && Array.isArray(masked.large_files)) {
    masked.large_files = masked.large_files.map((file) =>
      maskFileObject(file, false)
    );
  }

  if (masked.old_files && Array.isArray(masked.old_files)) {
    masked.old_files = masked.old_files.map((file) =>
      maskFileObject(file, false)
    );
  }

  if (masked.suspicious_duplicates && Array.isArray(masked.suspicious_duplicates)) {
    masked.suspicious_duplicates = masked.suspicious_duplicates.map((file) =>
      maskFileObject(file, false)
    );
  }

  if (masked.suspicious_temp && Array.isArray(masked.suspicious_temp)) {
    masked.suspicious_temp = masked.suspicious_temp.map((file) =>
      maskFileObject(file, false)
    );
  }

  if (masked.categories && typeof masked.categories === 'object') {
    const maskedCategories: Record<string, any> = {};
    for (const [key, value] of Object.entries(masked.categories)) {
      if (Array.isArray(value)) {
        maskedCategories[key] = value.map((file) =>
          maskFileObject(file, false)
        );
      } else {
        maskedCategories[key] = value;
      }
    }
    masked.categories = maskedCategories;
  }

  return masked;
}
