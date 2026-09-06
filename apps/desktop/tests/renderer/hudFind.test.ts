import { describe, expect, it } from 'vitest';

import {
  formatFindCount,
  matchFindShortcut,
  matchingMessageIds,
  wrapFindIndex,
} from '@/lib/hudFind';

function key(
  partial: Partial<{
    key: string;
    shiftKey: boolean;
    ctrlKey: boolean;
    metaKey: boolean;
    altKey: boolean;
  }>,
) {
  return {
    key: 'a',
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    ...partial,
  };
}

describe('hudFind', () => {
  it('eşleşen id’leri sırayla toplar', () => {
    expect(
      matchingMessageIds(
        [
          { id: 'a', content: 'GPU durumu' },
          { id: 'b', content: 'merhaba' },
          { id: 'c', content: 'gpu fan' },
        ],
        'gpu',
      ),
    ).toEqual(['a', 'c']);
    expect(matchingMessageIds([{ id: 'a', content: 'x' }], '  ')).toEqual([]);
    expect(
      matchingMessageIds(
        [
          {
            id: 'mcp',
            content: 'Hazır.',
            toolCalls: [
              {
                tool_name: 'mcp_call',
                display_name: 'MCP aracı çağır',
                arguments: { server: 'docs', tool: 'query-docs' },
              },
            ],
          },
        ],
        'query-docs',
      ),
    ).toEqual(['mcp']);
    expect(
      matchingMessageIds(
        [
          {
            id: 'body',
            content: 'Hazır.',
            toolCalls: [
              {
                tool_name: 'mcp_call',
                display_name: 'MCP aracı çağır',
                result: { result: { content: [{ type: 'text', text: 'zod docs' }] } },
              },
            ],
          },
        ],
        'zod docs',
      ),
    ).toEqual(['body']);
  });

  it('F3 sarmalar, sayaç 1-tabanlıdır', () => {
    expect(wrapFindIndex(1, 1, 2)).toBe(0);
    expect(wrapFindIndex(0, -1, 2)).toBe(1);
    expect(wrapFindIndex(-1, 1, 3)).toBe(0);
    expect(formatFindCount(0, 3)).toBe('1/3');
    expect(formatFindCount(0, 0)).toBe('0/0');
  });

  it('CodeMirror searchKeymap: Mod-f / F3 / Mod-g / Escape', () => {
    expect(matchFindShortcut(key({ key: 'f', ctrlKey: true }), false)).toBe('openFind');
    expect(matchFindShortcut(key({ key: 'F3' }), false)).toBe('findNext');
    expect(matchFindShortcut(key({ key: 'F3', shiftKey: true }), false)).toBe('findPrev');
    expect(matchFindShortcut(key({ key: 'g', ctrlKey: true }), false)).toBe('findNext');
    expect(matchFindShortcut(key({ key: 'g', ctrlKey: true, shiftKey: true }), false)).toBe(
      'findPrev',
    );
    expect(matchFindShortcut(key({ key: 'Enter' }), true)).toBe('findNext');
    expect(matchFindShortcut(key({ key: 'Enter', shiftKey: true }), true)).toBe('findPrev');
    expect(matchFindShortcut(key({ key: 'Escape' }), true)).toBe('clearFind');
    expect(matchFindShortcut(key({ key: 'Enter' }), false)).toBeNull();
    expect(matchFindShortcut(key({ key: 'Escape' }), false)).toBeNull();
  });
});
