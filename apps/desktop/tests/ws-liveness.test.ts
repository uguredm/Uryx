/** VS Code keepalive timeout — yarım açık soket. */

import { describe, expect, it } from 'vitest';

import { HOST_STALE_SILENCE_MS, shouldTerminateStaleSocket } from '../electron/host-tools/ws-liveness';

describe('VS Code host ws liveness', () => {
  it('açılıştan 45s sessizlik stale, 45s altı değil', () => {
    expect(shouldTerminateStaleSocket(44_999, 0)).toBe(false);
    expect(shouldTerminateStaleSocket(HOST_STALE_SILENCE_MS, 0)).toBe(true);
    expect(shouldTerminateStaleSocket(50_000, 10_000)).toBe(false);
    expect(shouldTerminateStaleSocket(55_000, 10_000)).toBe(true);
  });

  it('henüz açılmamış soketi kesmez', () => {
    expect(shouldTerminateStaleSocket(Date.now(), null)).toBe(false);
  });
});
