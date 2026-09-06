import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { HudHealthChip } from '@/components/hud/HudHealthChip';
import { useSystemStore } from '@/hooks/useSystemStatus';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

afterEach(() => {
  useChatStore.setState({ connection: 'closed' });
  useSystemStore.setState({ status: null });
  useUIStore.setState({ view: 'chat' });
});

describe('HudHealthChip', () => {
  it('sağlıklı bağlantıda gizlenir', () => {
    useChatStore.setState({ connection: 'open' });
    useSystemStore.setState({
      status: {
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
      },
    });
    const { container } = render(<HudHealthChip />);
    expect(container).toBeEmptyDOMElement();
  });

  it('model yokken Sistem görünümüne gider', () => {
    useChatStore.setState({ connection: 'open' });
    useSystemStore.setState({
      status: {
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
        model: { loaded: false, model_id: null, max_model_len: null, detail: null },
        host_bridge_connected: true,
        last_error: null,
        timestamp: '',
      },
    });
    render(<HudHealthChip />);
    fireEvent.click(screen.getByRole('button', { name: 'LOCAL MODEL' }));
    expect(useUIStore.getState().view).toBe('system');
  });
});
