/**
 * Enerji + sıfır geçişi VAD. Renderer'da ONNX yok.
 * `onSpeechStart` / `onAutoStop` imzası MicRecorder ile aynı.
 */

export interface VadFrameFeatures {
  rms: number;
  zcr: number;
}

export interface EnergyZcrVadOptions {
  noiseThreshold?: number;
  adaptiveNoiseFloor?: boolean;
  silenceTimeoutMs?: number;
  initialSilenceTimeoutMs?: number;
  now?: () => number;
  onLevel?: (level: number) => void;
  onSpeechStart?: () => void;
  onAutoStop?: () => void;
}

const SPEECH_HANGOVER_FRAMES = 5;
const MIN_SPEECH_ZCR = 0.005;
const MAX_SPEECH_ZCR = 0.25;

export function frameFeatures(samples: ArrayLike<number>): VadFrameFeatures {
  const length = samples.length;
  if (length === 0) return { rms: 0, zcr: 0 };
  let sum = 0;
  let crossings = 0;
  let previous = samples[0] ?? 0;
  for (let i = 0; i < length; i += 1) {
    const sample = samples[i] ?? 0;
    sum += sample * sample;
    if ((previous >= 0 && sample < 0) || (previous < 0 && sample >= 0)) {
      crossings += 1;
    }
    previous = sample;
  }
  return {
    rms: Math.sqrt(sum / length),
    zcr: crossings / length,
  };
}

export function isSpeechFrame(
  features: VadFrameFeatures,
  threshold: number,
  noiseFloor: number,
  adaptive: boolean,
): boolean {
  const activeThreshold = adaptive
    ? Math.max(threshold * 0.5, noiseFloor * 2.4 + 0.0015)
    : threshold;
  if (features.rms <= activeThreshold) return false;
  return features.zcr >= MIN_SPEECH_ZCR && features.zcr <= MAX_SPEECH_ZCR;
}

export function createEnergyZcrVad(options: EnergyZcrVadOptions = {}) {
  const threshold = options.noiseThreshold ?? 0.012;
  const adaptive = options.adaptiveNoiseFloor ?? true;
  const silenceTimeout = options.silenceTimeoutMs ?? 1600;
  const initialSilenceTimeout = options.initialSilenceTimeoutMs ?? 0;
  const now = options.now ?? (() => performance.now());
  const startedAt = now();
  let noiseFloor = Math.max(0.001, threshold / 3);
  let speechFrames = 0;
  let speechDetected = false;
  let lastVoiceAt = startedAt;
  let stopped = false;

  return {
    get speechDetected(): boolean {
      return speechDetected;
    },
    push(samples: ArrayLike<number>): 'continue' | 'auto-stop' {
      const features = frameFeatures(samples);
      options.onLevel?.(Math.min(features.rms * 8, 1));
      const speaking = isSpeechFrame(features, threshold, noiseFloor, adaptive);

      if (!speechDetected && !speaking) {
        noiseFloor = noiseFloor * 0.97 + features.rms * 0.03;
      }

      if (speaking) {
        speechFrames += 1;
        lastVoiceAt = now();
        if (!speechDetected && speechFrames >= SPEECH_HANGOVER_FRAMES) {
          speechDetected = true;
          options.onSpeechStart?.();
        }
        return 'continue';
      }

      speechFrames = 0;
      if (stopped) return 'auto-stop';
      const t = now();
      if (silenceTimeout > 0 && speechDetected && t - lastVoiceAt > silenceTimeout) {
        stopped = true;
        options.onAutoStop?.();
        return 'auto-stop';
      }
      if (
        initialSilenceTimeout > 0 &&
        !speechDetected &&
        t - startedAt > initialSilenceTimeout
      ) {
        stopped = true;
        options.onAutoStop?.();
        return 'auto-stop';
      }
      return 'continue';
    },
  };
}
