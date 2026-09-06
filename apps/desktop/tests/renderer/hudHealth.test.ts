import { describe, expect, it } from 'vitest';

import { describeHudHealth } from '@/lib/hudHealth';
import type { SystemStatus } from '@shared/api';

function status(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    services: [],
    metrics: {
      cpu_percent: 0,
      cpu_cores: 1,
      ram_total_mb: 1,
      ram_used_mb: 0,
      ram_percent: 0,
      gpu: {
        name: 'x',
        vram_total_mb: 0,
        vram_used_mb: 0,
        vram_percent: 0,
        utilization_percent: 0,
        temperature_c: null,
        driver_version: null,
        available: false,
      },
      disks: [],
      source: 'host',
      timestamp: '',
    },
    model: { loaded: true, model_id: 'qwen3-8b', max_model_len: 8192, detail: null },
    host_bridge_connected: true,
    last_error: null,
    timestamp: '',
    ...overrides,
  };
}

describe('describeHudHealth', () => {
  it('API kapalıyken offline döner', () => {
    expect(describeHudHealth('closed', null)?.label).toBe('NO SERVER');
    expect(describeHudHealth('closed', null, 'tr')?.label).toBe('SUNUCU YOK');
    expect(describeHudHealth('connecting', null)?.dot).toBe('starting');
  });

  it('model yüklenmediyse MODEL gösterir', () => {
    const issue = describeHudHealth(
      'open',
      status({ model: { loaded: false, model_id: null, max_model_len: null, detail: null } }),
    );
    expect(issue?.kind).toBe('degraded');
    expect(issue?.label).toBe('LOCAL MODEL');
  });

  it('sağlıklıysa gizlenir', () => {
    expect(describeHudHealth('open', status())).toBeNull();
  });
});
