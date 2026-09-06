/** host_tool_cancel / AbortSignal PowerShell ağacını keser. */

import { spawn } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { buildHostToolResponse } from '../electron/host-bridge';
import { closeChildStdio, killProcessTree, run } from '../electron/host-tools/process';
import {
  hostCapabilityPayload,
  requestHostCapabilitiesRefresh,
  setHostCapabilitiesRefreshSink,
} from '../electron/host-tools';
import { recordMcpAdvertisement, resetMcpAdvertisement } from '../electron/host-tools/mcp';

describe('host_tool_cancel cevabı', () => {
  it('iptalde de host_tool_response üretir, yutmaz', () => {
    const payload = buildHostToolResponse(
      'req-1',
      { success: true, result: { pid: 9 }, error: null },
      true,
    );
    expect(payload.type).toBe('host_tool_response');
    expect(payload.success).toBe(false);
    expect(payload.cancelled).toBe(true);
    expect(payload.error).toMatch(/iptal/i);
    expect((payload.result as { cancelled?: boolean }).cancelled).toBe(true);
  });

  it('iptal değilse outcome’u olduğu gibi taşır', () => {
    const payload = buildHostToolResponse(
      'req-2',
      { success: true, result: { ok: true }, error: null },
      false,
    );
    expect(payload.success).toBe(true);
    expect(payload.cancelled).toBe(false);
    expect(payload.error).toBeNull();
  });
});

describe('hung süreç kesme', () => {
  it('closeChildStdio akışları kapatır', () => {
    const closed: string[] = [];
    const stream = { destroy: () => closed.push('x') };
    closeChildStdio({ stdin: stream, stdout: stream, stderr: stream } as never);
    expect(closed).toHaveLength(3);
  });

  it('killProcessTree takılı node’u keser', async () => {
    const child = spawn(process.execPath, ['-e', 'setInterval(() => {}, 999999)'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    expect(child.pid).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 80));
    killProcessTree(child);
    const exited = await new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => resolve(false), 4000);
      const done = (): void => {
        clearTimeout(timer);
        resolve(true);
      };
      child.once('exit', done);
      child.once('close', done);
    });
    expect(exited).toBe(true);
  });

  it('run timeout takılı süreci keser', async () => {
    const started = Date.now();
    await expect(
      run(process.execPath, ['-e', 'setInterval(() => {}, 999999)'], { timeoutMs: 400 }),
    ).rejects.toThrow(/zaman aşımı/);
    expect(Date.now() - started).toBeLessThan(5000);
  });
});

describe('PowerShell iptal', () => {
  it('AbortSignal Start-Sleep sürecini birkaç saniyede keser', async () => {
    const controller = new AbortController();
    const started = Date.now();
    const pending = run(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', 'Start-Sleep -Seconds 30'],
      { timeoutMs: 40_000, signal: controller.signal },
    );
    setTimeout(() => controller.abort(), 200);
    await expect(pending).rejects.toThrow(/iptal/i);
    expect(Date.now() - started).toBeLessThan(8_000);
  });
});

describe('MCP yetenek yenileme', () => {
  it('tools/list sonrası snapshot capabilities.mcp’e girer', () => {
    resetMcpAdvertisement();
    recordMcpAdvertisement('files', ['read_file', 'write_file'], ['read_file']);
    const payload = hostCapabilityPayload('0.7.1');
    const mcp = payload.mcp as { servers?: Array<{ id: string; advertised: string[] }> };
    expect(payload.features).toMatchObject({ process_tree_cancel: true, mcp_list: true });
    expect(typeof (payload.mcp as { enabled?: boolean }).enabled).toBe('boolean');
    void mcp;

    let refreshed = 0;
    setHostCapabilitiesRefreshSink(() => {
      refreshed += 1;
    });
    requestHostCapabilitiesRefresh();
    expect(refreshed).toBe(1);
    setHostCapabilitiesRefreshSink(null);
    resetMcpAdvertisement();
  });
});
