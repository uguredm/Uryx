import { beforeEach, describe, expect, it } from 'vitest';
import type { WSToolConfirmRequest } from '@shared/ws';

import { setUiLanguage } from '@/lib/uiLocale';

import {
  buildToolConfirmResponse,
  canRememberConfirm,
  chatSocketLost,
  chatTurnIsActive,
  confirmArgumentEntries,
  confirmMatchesCall,
  displayResultFallback,
  flattenToolArgs,
  hudMessagePlainText,
  hudToolLabel,
  mcpConfirmImpact,
  mcpResultIsError,
  mcpResultText,
  mcpConfirmToolLabel,
  prettyDisplayText,
  quoteMessageText,
  stripHostDisplayMeta,
  summarizedToolStatus,
  toolDisplayStatus,
  pendingConfirmToReplace,
  sealDigest,
  shouldShowStreamingBubble,
  toolCardLabel,
  toolCardResult,
  toolResultIsRejected,
} from '@/lib/confirmResponse';

const base: WSToolConfirmRequest = {
  type: 'tool_confirm_request',
  request_id: 'req-1',
  tool_name: 'open_application',
  display_name: 'Uygulama aç',
  description: '',
  arguments: { name: 'Spotify' },
  risk_level: 'medium',
  impact: 'Uygulama açılır',
  fingerprint: 'fp-abc',
  remember_allowed: true,
  confirmation_ticket: 'tkt-9',
};

beforeEach(() => {
  setUiLanguage('tr');
});

describe('buildToolConfirmResponse', () => {
  it('onayda bilet, iz ve hatırla yollar', () => {
    expect(buildToolConfirmResponse(base, true, true)).toEqual({
      type: 'tool_confirm_response',
      request_id: 'req-1',
      approved: true,
      remember: true,
      fingerprint: 'fp-abc',
      confirmation_ticket: 'tkt-9',
    });
  });

  it('HIGH ve geri alınamazda remember kapalı kalır', () => {
    expect(canRememberConfirm({ ...base, risk_level: 'high' })).toBe(false);
    expect(canRememberConfirm({ ...base, irreversible: true })).toBe(false);
    expect(buildToolConfirmResponse({ ...base, risk_level: 'high' }, true, true).remember).toBe(
      false,
    );
  });

  it('form onayında url ve alanlar durur; hatırla kapalı', () => {
    const pending: WSToolConfirmRequest = {
      ...base,
      tool_name: 'browser_fill_form',
      remember_allowed: false,
      arguments: {
        url: 'https://example.com/kayit',
        fields: [{ index: 0, text: 'ali' }],
      },
    };
    expect(canRememberConfirm(pending)).toBe(false);
    const entries = Object.fromEntries(confirmArgumentEntries(pending));
    expect(entries.url).toBe('https://example.com/kayit');
    expect(entries.fields).toEqual([{ index: 0, text: 'ali' }]);
  });

  it('parmak izinin ilk 16 karakterini mühür olarak gösterir', () => {
    expect(sealDigest('abcdef12')).toBe('abcdef12');
    expect(sealDigest('0123456789abcdefDEADBEEF')).toBe('0123456789abcdef');
    expect(sealDigest('short')).toBe('');
    expect(sealDigest(undefined)).toBe('');
  });

  it('mcp_call HIGH hatırlanmaz; sunucu/araç etki metninde durur', () => {
    const mcp: WSToolConfirmRequest = {
      ...base,
      tool_name: 'mcp_call',
      display_name: 'MCP aracı çağır',
      risk_level: 'high',
      irreversible: true,
      remember_allowed: false,
      arguments: { server: 'docs', tool: 'query-docs', arguments: { q: 'zod' } },
      impact: 'Yerel MCP sunucusuna allowlist’li bir araç çağrısı gider.',
    };
    expect(canRememberConfirm(mcp)).toBe(false);
    expect(buildToolConfirmResponse(mcp, true, true).remember).toBe(false);
    expect(mcpConfirmToolLabel(mcp)).toMatch(/docs → query-docs/);
    expect(mcpConfirmImpact(mcp)).toMatch(/docs/);
    expect(mcpConfirmImpact(mcp)).toMatch(/query-docs/);
    expect(confirmArgumentEntries(mcp)).toEqual([
      ['sunucu', 'docs'],
      ['araç', 'query-docs'],
      ['q', 'zod'],
    ]);
    expect(flattenToolArgs('mcp_call', mcp.arguments)).toEqual(confirmArgumentEntries(mcp));
    expect(toolCardLabel('mcp_call', 'MCP aracı çağır', mcp.arguments)).toMatch(/docs → query-docs/);
    expect(hudToolLabel('mcp_call', 'MCP aracı çağır', mcp.arguments)).toBe('docs → query-docs');
    expect(hudToolLabel('open_application', 'Uygulama aç', { name: 'Spotify' })).toBe('Uygulama aç');
    expect(
      toolCardResult('mcp_call', {
        server: 'docs',
        tool: 'query-docs',
        result: { library: 'zod' },
        execution_policy: 'unsafe',
      }),
    ).toEqual({ library: 'zod' });
    expect(toolCardResult('open_application', { opened: true })).toEqual({ opened: true });
    expect(toolCardLabel('mcp_list_tools', 'MCP araçlarını listele', { server: 'docs' })).toMatch(
      /docs/,
    );
    expect(hudToolLabel('mcp_list_tools', 'MCP araçlarını listele', { server: 'docs' })).toBe(
      'docs',
    );
    expect(flattenToolArgs('mcp_list_tools', { server: 'docs' })).toEqual([['sunucu', 'docs']]);
    expect(
      mcpResultText('mcp_call', {
        result: { content: [{ type: 'text', text: 'zod docs' }], isError: false },
      }),
    ).toBe('zod docs');
    expect(
      mcpResultIsError('mcp_call', { result: { content: [{ type: 'text', text: 'nope' }], isError: true } }),
    ).toBe(true);
    expect(
      mcpResultText('mcp_list_tools', { server: 'docs', allowed: ['query-docs'], advertised: ['query-docs'] }),
    ).toMatch(/çağrılabilir: query-docs/);
    expect(
      mcpResultText('mcp_list_tools', {
        server: 'docs',
        allowed: [],
        advertised: ['secret-tool'],
        execution_policy: 'unsafe',
      }),
    ).toMatch(/çağrılabilir: \(yok\)/);
    expect(
      mcpResultText('mcp_list_tools', {
        server: 'docs',
        allowed: ['query-docs'],
        descriptions: [{ name: 'query-docs', description: 'Zod belgesi' }],
      }),
    ).toMatch(/query-docs — Zod belgesi/);
    expect(
      mcpResultText('mcp_call', { result: 'düz metin sonuç' }),
    ).toBe('düz metin sonuç');
    expect(
      mcpResultText('mcp_call', { result: { content: 'tek parça' } }),
    ).toBe('tek parça');
    expect(
      mcpResultText('mcp_call', { result: { structuredContent: { hits: 2 } } }),
    ).toMatch(/"hits": 2/);
    expect(
      mcpResultText('mcp_call', { result: { content: [], isError: true } }),
    ).toBe('MCP aracı hata döndürdü.');
    expect(
      stripHostDisplayMeta({
        server: 'docs',
        allowed: ['query-docs'],
        execution_policy: 'unsafe',
        output_truncated: true,
      }),
    ).toEqual({ server: 'docs', allowed: ['query-docs'] });
    expect(
      toolCardResult('mcp_list_tools', {
        server: 'docs',
        allowed: ['query-docs'],
        execution_policy: 'unsafe',
      }),
    ).toEqual({ server: 'docs', allowed: ['query-docs'] });
    expect(
      toolDisplayStatus('mcp_call', 'success', {
        result: { content: [{ type: 'text', text: 'nope' }], isError: true },
      }),
    ).toBe('failed');
    expect(toolDisplayStatus('open_application', 'success', { opened: true })).toBe('success');
    expect(
      flattenToolArgs('mcp_call', {
        server: 'docs',
        tool: 'query-docs',
        arguments: '{"q":"zod"}',
      }),
    ).toEqual([
      ['sunucu', 'docs'],
      ['araç', 'query-docs'],
      ['q', 'zod'],
    ]);
    expect(
      mcpResultText('mcp_call', {
        result: { content: [{ type: 'image', data: 'AAAA', mimeType: 'image/png' }] },
      }),
    ).toBe('1 medya parçası');
    const blob = 'A'.repeat(300);
    expect(
      JSON.stringify(
        toolCardResult('mcp_call', {
          result: { content: [{ type: 'image', data: blob }] },
        }),
      ),
    ).not.toContain(blob);
    expect(mcpResultText('mcp_call', { result: blob })).toBe('[300 karakter]');
    expect(prettyDisplayText('{"library":"zod"}')).toMatch(/"library": "zod"/);
    expect(
      mcpResultText('mcp_call', {
        result: { content: [{ type: 'text', text: '{"library":"zod"}' }] },
      }),
    ).toMatch(/"library": "zod"/);
    expect(
      summarizedToolStatus('mcp_call', {
        success: false,
        error: 'Kullanıcı bu işlemi reddetti.',
      }),
    ).toBe('rejected');
    expect(
      summarizedToolStatus('mcp_call', {
        success: true,
        result: { result: { content: [], isError: true } },
      }),
    ).toBe('failed');
    expect(
      hudMessagePlainText('Cevap', [
        {
          tool_name: 'mcp_call',
          display_name: 'MCP aracı çağır',
          arguments: { server: 'docs', tool: 'query-docs' },
          success: true,
          result: { result: { content: [{ type: 'text', text: 'zod docs' }] } },
        },
      ]),
    ).toMatch(/docs → query-docs · TAMAMLANDI[\s\S]*zod docs/);
    expect(
      quoteMessageText('', [
        {
          tool_name: 'mcp_call',
          result: { result: { content: [{ type: 'text', text: 'zod docs' }] } },
        },
      ]),
    ).toBe('zod docs');
    expect(quoteMessageText('  Cevap  ', [])).toBe('Cevap');
    expect(
      displayResultFallback({ content: [{ type: 'text', text: 'x' }], isError: false, _meta: {} }),
    ).toBe('');
    expect(displayResultFallback({ library: 'zod', isError: false })).toMatch(/"library": "zod"/);
    expect(hudToolLabel('mcp_call', 'MCP aracı çağır', {}, { server: 'docs', tool: 'query-docs' })).toBe(
      'docs → query-docs',
    );
    expect(
      flattenToolArgs('mcp_call', {}, { server: 'docs', tool: 'query-docs' }),
    ).toEqual([
      ['sunucu', 'docs'],
      ['araç', 'query-docs'],
    ]);
    expect(
      flattenToolArgs('mcp_call', {
        server: 'docs',
        tool: 'query-docs',
        arguments: { query: { library: 'zod' } },
      }),
    ).toEqual([
      ['sunucu', 'docs'],
      ['araç', 'query-docs'],
      ['query.library', 'zod'],
    ]);
    expect(shouldShowStreamingBubble('', '')).toBe(false);
    expect(shouldShowStreamingBubble('  ', '')).toBe(false);
    expect(shouldShowStreamingBubble('', 'düşün')).toBe(true);
    expect(shouldShowStreamingBubble('merhaba', '')).toBe(true);
  });

  it('ikinci onay birincinin request_id’sini değiştirirse eskisini işaretler', () => {
    const next = { ...base, request_id: 'req-2', tool_name: 'mcp_call' };
    expect(pendingConfirmToReplace(null, next)).toBeNull();
    expect(pendingConfirmToReplace(base, base)).toBeNull();
    expect(pendingConfirmToReplace(base, next)).toEqual(base);
  });

  it('yeni sohbet üretim veya onay varken turu keser', () => {
    expect(chatTurnIsActive(false, null)).toBe(false);
    expect(chatTurnIsActive(true, null)).toBe(true);
    expect(chatTurnIsActive(false, base)).toBe(true);
  });

  it('onay red/iptal/süre kartı reddedildi sayılır', () => {
    expect(toolResultIsRejected('Kullanıcı bu işlemi reddetti.')).toBe(true);
    expect(toolResultIsRejected('Kullanıcı işlemi iptal etti.')).toBe(true);
    expect(toolResultIsRejected('Kullanıcı onayı zaman aşımına uğradı.')).toBe(true);
    expect(toolResultIsRejected('MCP initialize zaman aşımı.')).toBe(false);
    expect(toolResultIsRejected(null)).toBe(false);
  });

  it('kopuk soket ve eşleşen tool_result onay modalını kapatır', () => {
    expect(chatSocketLost('closed')).toBe(true);
    expect(chatSocketLost('error')).toBe(true);
    expect(chatSocketLost('connecting')).toBe(false);
    expect(chatSocketLost('open')).toBe(false);
    expect(confirmMatchesCall('req-1', 'req-1')).toBe(true);
    expect(confirmMatchesCall('req-1', 'req-2')).toBe(false);
    expect(confirmMatchesCall(undefined, 'req-1')).toBe(false);
  });

  it('redde remember gitmez, bilet yine echo edilir', () => {
    const denied = buildToolConfirmResponse(base, false, true);
    expect(denied.approved).toBe(false);
    expect(denied.remember).toBe(false);
    expect(denied.confirmation_ticket).toBe('tkt-9');
    expect(denied.fingerprint).toBe('fp-abc');
  });
});
