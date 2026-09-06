import { describe, expect, it } from 'vitest';

import { openHistorySearch, useUIStore } from '@/stores/uiStore';

describe('openHistorySearch', () => {
  it('gerçek bir fonksiyondur ve geçmiş görünümünü açar', () => {
    expect(typeof openHistorySearch).toBe('function');
    useUIStore.setState({ view: 'chat', historySearchTick: 0 });
    openHistorySearch();
    const state = useUIStore.getState();
    expect(state.view).toBe('history');
    expect(state.historySearchTick).toBe(1);
    expect(typeof state.openHistorySearch).toBe('function');
  });
});
