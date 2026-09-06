/** Whisper metninden uyandırma ifadesini ve varsa devamındaki komutu çıkarır. */

const URYX_ALIASES = ['uryx', 'jarvis', 'carvis', 'cervis', 'jervis', 'larvis', 'yarvis', 'jarviz'];

export function extractWakeCommand(text: string, wakeWord: string): string | null {
  const cleanText = text.trim();
  const cleanWakeWord = wakeWord.trim().toLocaleLowerCase('tr-TR');
  if (!cleanText || !cleanWakeWord) return null;

  const aliases = cleanWakeWord === 'uryx' ? URYX_ALIASES : [cleanWakeWord];
  const words = aliases.map(escapeRegExp).join('|');
  const name = `(?:${words})(?:['’]?[ei])?`;
  const patterns = [
    new RegExp(
      `^\\s*(?:(?:hey|hei|haydi)\\s+)?${name}\\b(?:\\s+(?:uyan|dinle|baksana))?[\\s,;:!?.-]*(.*)$`,
      'iu',
    ),
    new RegExp(`^\\s*(?:uyan|dinle|baksana)(?:\\s+${name}\\b)?[\\s,;:!?.-]*(.*)$`, 'iu'),
  ];
  for (const pattern of patterns) {
    const match = cleanText.match(pattern);
    if (match) return (match[1] ?? '').trim();
  }
  return null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export type IdleWakeDecision = 'onnx_hit' | 'onnx_miss' | 'whisper_fallback';

export interface IdleWakeHost {
  status: () => Promise<{ usingFallback: boolean }>;
  pushPcm: (
    samples: number[],
    sampleRate: number,
  ) => Promise<{ hit: boolean; score?: number; reason: string }>;
}

/** Son N saniyelik PCM penceresi (IPC tavanı için). */
export function wakePcmWindow(samples: Float32Array, sampleRate: number, seconds = 1.5): Float32Array {
  const rate = sampleRate > 0 ? sampleRate : 16_000;
  const keep = Math.max(0, Math.min(samples.length, Math.floor(rate * seconds)));
  if (keep === 0) return new Float32Array(0);
  if (keep === samples.length) return samples;
  return samples.subarray(samples.length - keep);
}

export function resampleTo16k(samples: Float32Array, sampleRate: number): Float32Array {
  if (samples.length === 0) return new Float32Array(0);
  const rate = sampleRate > 0 ? sampleRate : 16_000;
  if (rate === 16_000) return Float32Array.from(samples);
  const outLength = Math.max(1, Math.floor((samples.length * 16_000) / rate));
  const out = new Float32Array(outLength);
  const scale = (samples.length - 1) / Math.max(outLength - 1, 1);
  for (let i = 0; i < outLength; i += 1) {
    const src = i * scale;
    const left = Math.floor(src);
    const right = Math.min(left + 1, samples.length - 1);
    const frac = src - left;
    out[i] = samples[left] * (1 - frac) + samples[right] * frac;
  }
  return out;
}

/**
 * Host ONNX hazırsa Whisper'sız sınıflandırır.
 * Model yoksa / host yoksa Whisper + extractWakeCommand yedeği.
 */
export async function classifyIdleWake(opts: {
  host?: IdleWakeHost;
  samples: Float32Array;
  sampleRate: number;
}): Promise<IdleWakeDecision> {
  if (!opts.host) return 'whisper_fallback';
  const status = await opts.host.status();
  if (status.usingFallback) return 'whisper_fallback';
  const window = wakePcmWindow(opts.samples, opts.sampleRate);
  const pcm16 = resampleTo16k(window, opts.sampleRate);
  try {
    const result = await opts.host.pushPcm(Array.from(pcm16), 16_000);
    return result.hit ? 'onnx_hit' : 'onnx_miss';
  } catch {
    return 'whisper_fallback';
  }
}
