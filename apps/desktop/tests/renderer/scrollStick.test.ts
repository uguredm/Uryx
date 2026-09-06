import { describe, expect, it } from 'vitest';

import {
  isNearBottom,
  lastCopyableText,
  shouldAutoScroll,
  STICKY_MARGIN_PX,
} from '@/lib/scrollStick';

describe('scrollStick', () => {
  it('60px içinde dip sayar, yukarıda saymaz', () => {
    expect(
      isNearBottom({ scrollHeight: 1000, scrollTop: 940, clientHeight: 60 }),
    ).toBe(true);
    expect(
      isNearBottom({ scrollHeight: 1000, scrollTop: 800, clientHeight: 60 }),
    ).toBe(false);
    expect(STICKY_MARGIN_PX).toBe(60);
  });

  it('yapışık değilken otomatik kaydırmaz', () => {
    expect(shouldAutoScroll(true)).toBe(true);
    expect(shouldAutoScroll(false)).toBe(false);
  });

  it('son dolu mesajı kopyalar', () => {
    expect(lastCopyableText([])).toBeNull();
    expect(lastCopyableText([{ content: 'ilk' }, { content: '   ' }, { content: 'son\n' }])).toBe(
      'son',
    );
  });
});
