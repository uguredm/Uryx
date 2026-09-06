import { describe, expect, it } from 'vitest';

import { readEmbeddingFallback } from '@/lib/hudEmbedding';

describe('readEmbeddingFallback', () => {
  it('hash fallback açıkken HUD uyarısı gösterilir', () => {
    expect(
      readEmbeddingFallback({
        embedding: { model: 'hash-fallback', dimension: 384, fallback_active: true },
      }),
    ).toBe(true);
  });

  it('MiniLM yüklüyken uyarı yok', () => {
    expect(
      readEmbeddingFallback({
        embedding: { fallback_active: false, model: 'paraphrase-multilingual-MiniLM-L12-v2' },
      }),
    ).toBe(false);
  });

  it('bozuk config patlatmaz', () => {
    expect(readEmbeddingFallback(null)).toBe(false);
    expect(readEmbeddingFallback({})).toBe(false);
  });
});
