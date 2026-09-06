import { describe, expect, it } from 'vitest';

import { QUOTE_SEPARATOR } from '@/lib/composerQuote';
import { quoteToComposer, useUIStore } from '@/stores/uiStore';

describe('quoteToComposer', () => {
  it('boşu atar, doluyu chat + tick yapar', () => {
    useUIStore.setState({ view: 'history', composerQuote: '', composerQuoteTick: 0 });
    expect(quoteToComposer('   ')).toBe(false);
    expect(useUIStore.getState().composerQuoteTick).toBe(0);

    expect(quoteToComposer('GPU')).toBe(true);
    const state = useUIStore.getState();
    expect(state.view).toBe('chat');
    expect(state.composerQuoteTick).toBe(1);
    expect(state.composerQuote).toContain('> GPU');
    expect(state.composerQuote).toContain(QUOTE_SEPARATOR);
  });
});
