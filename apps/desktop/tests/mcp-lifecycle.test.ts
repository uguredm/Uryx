/** Eşzamanlı mcp_call, kapatırken kesme, ayar değişimi. */

import { spawn } from 'node:child_process';

import { afterEach, describe, expect, it } from 'vitest';

import {
  abortInFlightMcp,
  acquireMcpSlot,
  isMcpRuntimeStopped,
  mcpInFlightCount,
  mcpSettingsNeedCapabilityRefresh,
  mcpSettingsRequireAbort,
  onMcpSettingsChanged,
  peekMcpAdvertisement,
  recordMcpAdvertisement,
  releaseMcpSlot,
  resumeMcpRuntime,
  shutdownMcpRuntime,
  watchMcpChild,
} from '../electron/host-tools/mcp';

afterEach(() => {
  abortInFlightMcp();
  resumeMcpRuntime();
});

describe('MCP yaşam döngüsü', () => {
  it('ikinci eşzamanlı MCP slotunu reddeder', () => {
    acquireMcpSlot();
    expect(() => acquireMcpSlot()).toThrow(/Aynı anda bir MCP süreci/);
    releaseMcpSlot();
    acquireMcpSlot();
    releaseMcpSlot();
  });

  it('MCP kapanınca veya sunucu listesi değişince in-flight kesilir', () => {
    expect(
      mcpSettingsRequireAbort(
        { mcpEnabled: true, mcpServers: [{ id: 'docs' }] },
        { mcpEnabled: false, mcpServers: [{ id: 'docs' }] },
      ),
    ).toBe(true);
    expect(
      mcpSettingsRequireAbort(
        { mcpEnabled: true, mcpServers: [{ id: 'docs' }] },
        { mcpEnabled: true, mcpServers: [{ id: 'time' }] },
      ),
    ).toBe(true);
    expect(
      mcpSettingsRequireAbort(
        { mcpEnabled: true, mcpServers: [{ id: 'docs' }] },
        { mcpEnabled: true, mcpServers: [{ id: 'docs' }] },
      ),
    ).toBe(false);
    expect(
      mcpSettingsRequireAbort(
        {
          mcpEnabled: true,
          mcpServers: [{ id: 'docs', command: 'npx', args: ['-y', 'old'], allowedTools: ['query-docs'] }],
        },
        {
          mcpEnabled: true,
          mcpServers: [{ id: 'docs', command: 'npx', args: ['-y', 'new'], allowedTools: ['query-docs'] }],
        },
      ),
    ).toBe(true);
    expect(
      mcpSettingsRequireAbort(
        {
          mcpEnabled: true,
          mcpServers: [{ id: 'docs', env: { CONTEXT7_API_KEY: 'a' } }],
        },
        {
          mcpEnabled: true,
          mcpServers: [{ id: 'docs', env: { CONTEXT7_API_KEY: 'b' } }],
        },
      ),
    ).toBe(true);
    expect(
      mcpSettingsNeedCapabilityRefresh(
        { mcpEnabled: false, mcpServers: [{ id: 'docs' }] },
        { mcpEnabled: true, mcpServers: [{ id: 'docs' }] },
      ),
    ).toBe(true);
    expect(
      mcpSettingsNeedCapabilityRefresh(
        { mcpEnabled: true, mcpServers: [{ id: 'docs' }] },
        { mcpEnabled: true, mcpServers: [{ id: 'docs' }] },
      ),
    ).toBe(false);
  });

  it('abortInFlightMcp takılı çocuğu keser ve fail çağırır', async () => {
    const child = spawn(process.execPath, ['-e', 'setInterval(() => {}, 999999)'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    const failed = new Promise<Error>((resolve) => {
      watchMcpChild(child, resolve);
    });
    expect(mcpInFlightCount()).toBe(1);
    expect(abortInFlightMcp('MCP kapatıldı.')).toBe(1);
    expect(mcpInFlightCount()).toBe(0);
    await expect(failed).resolves.toMatchObject({ message: 'MCP kapatıldı.' });
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

  it('ayar sıfırlama ilan önbelleğini siler ve runtime’ı durdurur', () => {
    recordMcpAdvertisement('docs', ['query-docs', 'hf_jobs'], ['query-docs']);
    expect(peekMcpAdvertisement('docs')?.allowed).toEqual(['query-docs']);
    onMcpSettingsChanged(
      { mcpEnabled: true, mcpServers: [{ id: 'docs' }] },
      { mcpEnabled: false, mcpServers: [] },
    );
    expect(peekMcpAdvertisement('docs')).toBeUndefined();
    expect(isMcpRuntimeStopped()).toBe(true);
    expect(() => acquireMcpSlot()).toThrow(/durduruldu|kapatıldı/);
  });

  it('çıkış kuyruktaki spawn’ı da keser', () => {
    acquireMcpSlot();
    releaseMcpSlot();
    expect(shutdownMcpRuntime()).toBe(0);
    expect(isMcpRuntimeStopped()).toBe(true);
    expect(() => acquireMcpSlot()).toThrow(/durduruldu|kapatıldı/);
  });
});
