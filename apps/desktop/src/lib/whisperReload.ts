/** Whisper model değişimi — GPU uyarısı (Faz 4.3). */

import { tNow } from '@/lib/tNow';

export function whisperGpuContentionHint(model: string, device: string): string | null {
  const onGpu = device.toLowerCase() === 'cuda' || device.toLowerCase() === 'gpu';
  if (model === 'large-v3' && onGpu) {
    return tNow('settings.whisperGpuHint');
  }
  return null;
}
