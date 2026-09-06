/** VS Code permanent failure + discord.js auth close — reconnect yok. */

import { describe, expect, it } from 'vitest';

import { HOST_AUTH_CLOSE_CODE, shouldGiveUpHostReconnect } from '../electron/host-tools/host-close';

describe('VS Code host auth close', () => {
  it('4401 vazgeçer, ağ kopması vazgeçmez', () => {
    expect(shouldGiveUpHostReconnect(HOST_AUTH_CLOSE_CODE)).toBe(true);
    expect(shouldGiveUpHostReconnect(1006)).toBe(false);
    expect(shouldGiveUpHostReconnect(1001)).toBe(false);
    expect(shouldGiveUpHostReconnect(1012)).toBe(false);
    expect(shouldGiveUpHostReconnect(1000)).toBe(false);
  });
});
