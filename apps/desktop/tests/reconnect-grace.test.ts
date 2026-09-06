/** VS Code ReconnectionShortGraceTime — 5dk sonra vazgeç. */

import { describe, expect, it } from 'vitest';

import {
  HOST_RECONNECT_GRACE_MS,
  shouldGiveUpReconnectAfterGrace,
} from '../electron/host-tools/reconnect-grace';

describe('VS Code reconnect grace', () => {
  it('5dk dolunca vazgeçer, öncesi ve boş başlangıç vazgeçmez', () => {
    expect(shouldGiveUpReconnectAfterGrace(null, 10_000)).toBe(false);
    expect(shouldGiveUpReconnectAfterGrace(0, HOST_RECONNECT_GRACE_MS - 1)).toBe(false);
    expect(shouldGiveUpReconnectAfterGrace(0, HOST_RECONNECT_GRACE_MS)).toBe(true);
    expect(HOST_RECONNECT_GRACE_MS).toBe(5 * 60 * 1000);
  });
});
