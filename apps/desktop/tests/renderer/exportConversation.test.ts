import { describe, expect, it } from 'vitest';

import { setUiLanguage } from '@/lib/uiLocale';

import {
  canExportConversation,
  exportConversationMarkdown,
  exportFilename,
  formatConversationMarkdown,
  sanitizeExportFilename,
  titleFromMessages,
} from '@/lib/exportConversation';

describe('exportConversation', () => {
  it('boş ve yol karakterlerini temizler', () => {
    setUiLanguage('tr');
    expect(sanitizeExportFilename('  ')).toBe('Sohbet');
    expect(sanitizeExportFilename('a/b\\c:d')).toBe('a b c d');
  });

  it('zaman damgalı md adı üretir', () => {
    const name = exportFilename('Fatura sorusu', new Date('2026-08-16T02:45:00.000Z'));
    expect(name).toBe('uryx-Fatura sorusu-2026-08-16T02-45.md');
  });

  it('ilk kullanıcı satırını başlık yapar, boş sohbeti indirmez', () => {
    setUiLanguage('tr');
    expect(titleFromMessages([])).toBe('Sohbet');
    expect(
      titleFromMessages([
        { role: 'assistant', content: 'merhaba' },
        { role: 'user', content: '  GPU durumu  ' },
      ]),
    ).toBe('GPU durumu');
    expect(canExportConversation([{ role: 'user', content: '   ' }])).toBe(false);
  });

  it('masaüstünde native kaydeti blob’dan önce dener', async () => {
    const saveFile = async () => ({ canceled: false, filePaths: ['C:\\Users\\me\\sohbet.md'] });
    window.uryx = { dialog: { saveFile } } as unknown as Window['uryx'];
    const ok = await exportConversationMarkdown({
      title: 'GPU',
      messages: [{ role: 'user', content: 'merhaba' }],
    });
    expect(ok).toBe(true);
    delete window.uryx;
  });

  it('LobeChat tarzı rol başlıklı markdown yazar', () => {
    setUiLanguage('tr');
    const md = formatConversationMarkdown({
      title: 'GPU',
      messages: [
        { role: 'user', content: 'yük nedir?' },
        { role: 'assistant', content: 'düşük' },
        { role: 'assistant', content: '   ' },
      ],
    });
    expect(md).toContain('# GPU');
    expect(md).toContain('##### Kullanıcı:');
    expect(md).toContain('yük nedir?');
    expect(md).toContain('##### Uryx:');
    expect(md).toContain('düşük');
    expect(md.match(/##### Uryx:/g)?.length).toBe(1);
  });

  it('MCP araç satırını ve boş cevaplı turu yazar', () => {
    const md = formatConversationMarkdown({
      title: 'MCP',
      messages: [
        {
          role: 'assistant',
          content: '',
          toolCalls: [
            {
              tool_name: 'mcp_call',
              display_name: 'MCP aracı çağır',
              arguments: { server: 'docs', tool: 'query-docs' },
              success: true,
              result: { result: { content: [{ type: 'text', text: 'zod docs' }] } },
            },
          ],
        },
      ],
    });
    expect(md).toContain('docs → query-docs · TAMAMLANDI');
    expect(md).toContain('zod docs');
    expect(
      canExportConversation([
        {
          role: 'assistant',
          content: '   ',
          meta: {
            tool_calls: [
              {
                tool_name: 'mcp_list_tools',
                display_name: 'MCP araçlarını listele',
                arguments: { server: 'docs' },
                success: true,
              },
            ],
          },
        },
      ]),
    ).toBe(true);
  });
});
