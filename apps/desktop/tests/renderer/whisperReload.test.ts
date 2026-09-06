import { describe, expect, it } from 'vitest';

import { whisperGpuContentionHint } from '@/lib/whisperReload';

describe('whisperGpuContentionHint', () => {
  it('large-v3 + cuda iken 8B kart uyarısı verir', () => {
    const hint = whisperGpuContentionHint('large-v3', 'cuda');
    expect(hint).toMatch(/8B/i);
    expect(hint).toMatch(/CPU/i);
  });

  it('CPU Whisper veya küçük modelde uyarı yok', () => {
    expect(whisperGpuContentionHint('large-v3', 'cpu')).toBeNull();
    expect(whisperGpuContentionHint('medium', 'cuda')).toBeNull();
  });
});
