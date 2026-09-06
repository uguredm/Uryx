import { describe, expect, it } from 'vitest';

import { matchChatShortcut } from '@/lib/chatShortcuts';

describe('chatShortcuts', () => {
  it('Ctrl+Shift+O yeni sohbet, Shift+Esc odak', () => {
    expect(
      matchChatShortcut({ key: 'o', shiftKey: true, ctrlKey: true, metaKey: false }),
    ).toBe('newChat');
    expect(
      matchChatShortcut({ key: 'Escape', shiftKey: true, ctrlKey: false, metaKey: false }),
    ).toBe('focusComposer');
  });

  it('düz Escape dönüş, preventDefault ve Ctrl+K yok', () => {
    expect(
      matchChatShortcut({ key: 'Escape', shiftKey: false, ctrlKey: false, metaKey: false }),
    ).toBe('returnChat');
    expect(
      matchChatShortcut({
        key: 'Escape',
        shiftKey: false,
        ctrlKey: false,
        metaKey: false,
        defaultPrevented: true,
      }),
    ).toBeNull();
    expect(
      matchChatShortcut({ key: 'k', shiftKey: false, ctrlKey: true, metaKey: false }),
    ).toBeNull();
  });
});
