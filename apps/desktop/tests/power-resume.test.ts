/** VS Code onDidResumeOS + tunnel resume hız kapısı. */

import { describe, expect, it } from 'vitest';

import { HostBridgeClient } from '../electron/host-bridge';
import {
  shouldForceReconnectOnResume,
  shouldScheduleReconnectWhileAwake,
} from '../electron/host-tools/power-resume';

describe('VS Code power resume', () => {
  it('ilk resume bağlanır, 2.5s içindeki ikinci atılır', () => {
    expect(shouldForceReconnectOnResume(1000, null)).toBe(true);
    expect(shouldForceReconnectOnResume(2000, 1000)).toBe(false);
    expect(shouldForceReconnectOnResume(3499, 1000)).toBe(false);
    expect(shouldForceReconnectOnResume(3500, 1000)).toBe(true);
  });

  it('uykuda reconnect planlanmaz', () => {
    expect(shouldScheduleReconnectWhileAwake(true, false)).toBe(false);
    expect(shouldScheduleReconnectWhileAwake(false, true)).toBe(false);
    expect(shouldScheduleReconnectWhileAwake(false, false)).toBe(true);
  });

  it('başlamamış köprü resume ile bağlanmaz; debounce ikinciyi yutar', () => {
    const bridge = new HostBridgeClient();
    expect(bridge.handlePowerResume(1000)).toBe(false);
    expect(bridge.handlePowerResume(2000)).toBe(false);
  });
});
