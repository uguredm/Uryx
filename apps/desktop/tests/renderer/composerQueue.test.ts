import { describe, expect, it } from 'vitest';

import { COMPOSER_QUEUE_CAP, enqueueComposer, shiftComposer } from '@/lib/composerQueue';

describe('composerQueue', () => {
  it('boşu atar, tavanı keser', () => {
    expect(enqueueComposer('  ', [])).toEqual([]);
    const full = Array.from({ length: COMPOSER_QUEUE_CAP }, (_, i) => `m${i}`);
    expect(enqueueComposer('fazla', full)).toEqual(full);
  });

  it('sıradaki mesajı önden alır', () => {
    const queued = enqueueComposer('ikinci', enqueueComposer('ilk', []));
    expect(queued).toEqual(['ilk', 'ikinci']);
    expect(shiftComposer(queued)).toEqual({ next: 'ilk', rest: ['ikinci'] });
  });
});
