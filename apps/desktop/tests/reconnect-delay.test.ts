/** VS Code TIMES + botocore full jitter. */

import { describe, expect, it } from 'vitest';

import { HOST_RECONNECT_TIMES_MS, reconnectDelayMs } from '../electron/host-tools/reconnect-delay';

describe('VS Code / botocore reconnect delay', () => {
  it('ilk tur 0, sonraki TIMES tavanında jitter', () => {
    expect(reconnectDelayMs(1, () => 0.5)).toBe(0);
    expect(reconnectDelayMs(2, () => 0.5)).toBe(2_500);
    expect(reconnectDelayMs(4, () => 0.5)).toBe(5_000);
    expect(reconnectDelayMs(9, () => 0.5)).toBe(15_000);
    expect(reconnectDelayMs(20, () => 0.5)).toBe(15_000);
    expect(HOST_RECONNECT_TIMES_MS[HOST_RECONNECT_TIMES_MS.length - 1]).toBe(30_000);
  });

  it('random 0 ve 1 tavanı aşmaz', () => {
    expect(reconnectDelayMs(2, () => 0)).toBe(0);
    expect(reconnectDelayMs(2, () => 1)).toBe(5_000);
    expect(reconnectDelayMs(2, () => 1.5)).toBe(5_000);
  });
});
