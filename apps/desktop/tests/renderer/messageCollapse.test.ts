import { describe, expect, it } from 'vitest';

import {
  BUBBLE_COLLAPSE_MAX_PX,
  HUD_COLLAPSE_MAX_PX,
  shouldCollapseMessage,
} from '@/lib/messageCollapse';

describe('messageCollapse', () => {
  it('Mattermost gibi scrollHeight tavanı aşınca kısaltır', () => {
    expect(shouldCollapseMessage(601, BUBBLE_COLLAPSE_MAX_PX)).toBe(true);
    expect(shouldCollapseMessage(600, BUBBLE_COLLAPSE_MAX_PX)).toBe(false);
    expect(shouldCollapseMessage(241, HUD_COLLAPSE_MAX_PX)).toBe(true);
    expect(shouldCollapseMessage(100, HUD_COLLAPSE_MAX_PX)).toBe(false);
  });
});
