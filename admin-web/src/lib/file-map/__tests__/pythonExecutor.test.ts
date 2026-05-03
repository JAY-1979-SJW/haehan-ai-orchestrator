/**Tests for pythonExecutor HTTP client.*/

import { callPythonExecutor } from '../pythonExecutor';

// Mock fetch
global.fetch = jest.fn();

describe('callPythonExecutor', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    delete process.env.FILE_MAP_EXECUTOR_URL;
  });

  it('should use default executor URL when FILE_MAP_EXECUTOR_URL not set', async () => {
    const mockResponse = {
      ok: true,
      run_id: 'test-run-123',
      dry_run: true,
      success_count: 2,
      succeeded: ['/tmp/file1.txt', '/tmp/file2.txt'],
      failed_count: 0,
      failed: [],
      error: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue(mockResponse),
    });

    const result = await callPythonExecutor({
      dry_run: true,
      plans: [],
      base_target_dir: '/tmp/test',
    });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('http://file-map-executor:8510'),
      expect.any(Object)
    );
  });

  it('should use FILE_MAP_EXECUTOR_URL when provided', async () => {
    process.env.FILE_MAP_EXECUTOR_URL = 'http://custom-executor:9999';

    const mockResponse = {
      ok: true,
      run_id: 'test-run-456',
      dry_run: true,
      success_count: 1,
      succeeded: [],
      failed_count: 0,
      failed: [],
      error: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue(mockResponse),
    });

    await callPythonExecutor({
      dry_run: true,
      plans: [],
      base_target_dir: '/tmp/test',
    });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('http://custom-executor:9999'),
      expect.any(Object)
    );
  });

  it('should POST to /cleanup/execute endpoint', async () => {
    const mockResponse = {
      ok: true,
      run_id: 'test-789',
      dry_run: true,
      success_count: 0,
      succeeded: [],
      failed_count: 0,
      failed: [],
      error: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue(mockResponse),
    });

    const payload = {
      dry_run: true,
      approval_token: 'user-approved-cleanup-test',
      plans: [],
      base_target_dir: '/tmp/test',
    };

    await callPythonExecutor(payload);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/cleanup/execute'),
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })
    );
  });

  it('should include request payload in body', async () => {
    const mockResponse = {
      ok: true,
      run_id: 'test-payload',
      dry_run: true,
      success_count: 0,
      succeeded: [],
      failed_count: 0,
      failed: [],
      error: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue(mockResponse),
    });

    const payload = {
      dry_run: true,
      approval_token: 'token-123',
      base_target_dir: '/tmp/test',
      plans: [{ source: '/tmp/a', target: '/tmp/b', confirmed: true }],
    };

    await callPythonExecutor(payload);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: JSON.stringify(payload),
      })
    );
  });

  it('should adapt executor response to admin-web format', async () => {
    const executorResponse = {
      ok: true,
      run_id: 'executor-run-id',
      dry_run: true,
      success_count: 2,
      succeeded: ['/tmp/file1', '/tmp/file2'],
      failed_count: 1,
      failed: ['/tmp/file3'],
      error: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(executorResponse),
    });

    const result = await callPythonExecutor({
      dry_run: true,
      package_id: 'pkg-123',
      plans: [],
      base_target_dir: '/tmp/test',
    }) as Record<string, any>;

    // Should have admin-web structure
    expect(result.ok).toBe(true);
    expect(result.result).toBeDefined();
    expect(result.result.run_id).toBe('executor-run-id');
    expect(result.result.package_id).toBe('pkg-123');
    expect(result.result.success_count).toBe(2);
    expect(result.result.failed_count).toBe(1);
    expect(result.result.succeeded).toEqual(['/tmp/file1', '/tmp/file2']);
    expect(result.result.failed).toEqual(['/tmp/file3']);
    expect(result.result.skipped_count).toBe(0);
    expect(result.result.conflict_count).toBe(0);
  });

  it('should handle executor error response', async () => {
    const executorError = {
      ok: false,
      error: 'Invalid path',
      status_code: 400,
    };

    (global.fetch as any).mockResolvedValue({
      ok: false,
      status: 400,
      json: vi.fn().mockResolvedValue(executorError),
    });

    const result = await callPythonExecutor({
      dry_run: true,
      plans: [],
      base_target_dir: '/home/invalid',
    }) as Record<string, any>;

    expect(result.ok).toBe(false);
    expect(result.error).toBeDefined();
    expect(result.error).toContain('Invalid path');
  });

  it('should handle fetch network error', async () => {
    (global.fetch as any).mockRejectedValueOnce(
      new Error('Network timeout')
    );

    const result = await callPythonExecutor({
      dry_run: true,
      plans: [],
      base_target_dir: '/tmp/test',
    }) as Record<string, any>;

    expect(result.ok).toBe(false);
    expect(result.error).toContain('Network timeout');
  });

  it('should NOT use child_process.spawn', () => {
    // This test verifies that spawn is not imported/used
    const code = require('fs').readFileSync(
      require.resolve('../pythonExecutor.ts'),
      'utf-8'
    );
    expect(code).not.toMatch(/spawn/);
    expect(code).not.toMatch(/child_process/);
    expect(code).not.toMatch(/resolveCleanupExecutorPath/);
  });

  it('should set timeout for fetch call', async () => {
    const mockResponse = {
      ok: true,
      run_id: 'test-timeout',
      dry_run: true,
      success_count: 0,
      succeeded: [],
      failed_count: 0,
      failed: [],
      error: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue(mockResponse),
    });

    await callPythonExecutor({
      dry_run: true,
      plans: [],
      base_target_dir: '/tmp/test',
    });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        signal: expect.anything(),
      })
    );
  });
});
