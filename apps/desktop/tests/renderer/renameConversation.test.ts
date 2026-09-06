import { describe, expect, it } from 'vitest';

import { RENAME_TITLE_MAX, sanitizeRenameTitle } from '@/lib/renameConversation';

describe('sanitizeRenameTitle', () => {
  it('boşu reddeder, uzunluğu keser', () => {
    expect(sanitizeRenameTitle('   ')).toBeNull();
    expect(sanitizeRenameTitle('  Spotify aç  ')).toBe('Spotify aç');
    expect(sanitizeRenameTitle('x'.repeat(RENAME_TITLE_MAX + 8))).toHaveLength(RENAME_TITLE_MAX);
  });
});
