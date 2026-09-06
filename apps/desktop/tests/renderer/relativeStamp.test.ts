import { describe, expect, it } from 'vitest';

import { relativeTimeLabel } from '@/lib/relativeStamp';

describe('relativeStamp', () => {
  it('Zulip eşikleri: az önce, dk, dün, 90 gün', () => {
    const now = new Date('2026-08-16T12:00:00');
    expect(relativeTimeLabel(new Date('2026-08-16T11:59:00'), now, 'tr')).toBe('Az önce');
    expect(relativeTimeLabel(new Date('2026-08-16T11:40:00'), now, 'tr')).toBe('20 dk önce');
    expect(relativeTimeLabel(new Date('2026-08-16T10:00:00'), now, 'tr')).toBe('2 saat önce');
    expect(relativeTimeLabel(new Date('2026-08-15T10:00:00'), now, 'tr')).toBe('Dün');
    expect(relativeTimeLabel(new Date('2026-08-01T12:00:00'), now, 'tr')).toBe('15 gün önce');
    expect(relativeTimeLabel(new Date('2026-01-01T12:00:00'), now, 'tr')).toMatch(/Oca/i);
  });
});
