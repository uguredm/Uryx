import { describe, expect, it } from 'vitest';

import { buildReadiness, shouldShowFirstRun } from '@/lib/firstRun';
import { remainingConfirmMs, TOOL_CONFIRM_TIMEOUT_MS } from '@/components/chat/ToolConfirmModal';

describe('first-run readiness', () => {
  it('tüm maddeler hazırken listeyi gizler', () => {
    const items = buildReadiness({
      chatOpen: true,
      modelLoaded: true,
      downServices: [],
    });
    expect(items.every((item) => item.ready)).toBe(true);
    expect(shouldShowFirstRun(items, false)).toBe(false);
  });

  it('API veya model yokken gösterir, kapatılınca gizler', () => {
    const items = buildReadiness({
      chatOpen: false,
      modelLoaded: false,
      downServices: ['llm'],
    });
    expect(items.some((item) => !item.ready)).toBe(true);
    expect(shouldShowFirstRun(items, false)).toBe(true);
    expect(shouldShowFirstRun(items, true)).toBe(false);
  });

  it('MCP açık ve sunucu yokken ayarlar maddesi bekler', () => {
    const empty = buildReadiness({
      chatOpen: true,
      modelLoaded: true,
      downServices: [],
      mcpEnabled: true,
      mcpServerCount: 0,
    });
    expect(empty.find((item) => item.id === 'mcp')?.ready).toBe(false);
    expect(shouldShowFirstRun(empty, false)).toBe(true);
    const filled = buildReadiness({
      chatOpen: true,
      modelLoaded: true,
      downServices: [],
      mcpEnabled: true,
      mcpServerCount: 2,
    });
    expect(filled.find((item) => item.id === 'mcp')?.ready).toBe(true);
    expect(shouldShowFirstRun(filled, false)).toBe(false);
    const off = buildReadiness({
      chatOpen: true,
      modelLoaded: true,
      downServices: [],
      mcpEnabled: false,
    });
    expect(off.some((item) => item.id === 'mcp')).toBe(false);
  });

  it('İngilizce etiket üretir', () => {
    const items = buildReadiness({
      chatOpen: false,
      modelLoaded: false,
      downServices: ['llm'],
    });
    expect(items.find((item) => item.id === 'api')?.label).toBe('Local server');
    expect(items.find((item) => item.id === 'model')?.hint).toContain('GGUF');
    expect(
      buildReadiness({
        chatOpen: false,
        modelLoaded: false,
        downServices: ['llm'],
        language: 'tr',
      }).find((item) => item.id === 'api')?.label,
    ).toBe('Yerel sunucu');
  });
});

describe('tool confirm countdown', () => {
  it('kalan süreyi sıkıştırır', () => {
    expect(remainingConfirmMs(1_000, 1_000)).toBe(TOOL_CONFIRM_TIMEOUT_MS);
    expect(remainingConfirmMs(1_000, 1_000 + TOOL_CONFIRM_TIMEOUT_MS + 50)).toBe(0);
    expect(remainingConfirmMs(1_000, 1_000 + 5_000)).toBe(TOOL_CONFIRM_TIMEOUT_MS - 5_000);
  });
});
