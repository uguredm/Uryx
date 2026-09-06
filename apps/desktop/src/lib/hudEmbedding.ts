/** `/system/config` embedding.fallback_active — HUD SYSTEM STATUS, banner değil. */

export function readEmbeddingFallback(config: unknown): boolean {
  if (!config || typeof config !== 'object') return false;
  const embedding = (config as { embedding?: { fallback_active?: unknown } }).embedding;
  return embedding?.fallback_active === true;
}
