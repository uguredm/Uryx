import { describe, expect, it } from 'vitest';

import { createEnergyZcrVad, frameFeatures, isSpeechFrame } from '@/lib/vad';

function sine(length: number, freq: number, sampleRate = 48_000, amp = 0.3): Float32Array {
  const out = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    out[i] = Math.sin((2 * Math.PI * freq * i) / sampleRate) * amp;
  }
  return out;
}

function noise(length: number, amp = 0.3): Float32Array {
  const out = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    out[i] = (i % 2 === 0 ? 1 : -1) * amp;
  }
  return out;
}

describe('frameFeatures / isSpeechFrame', () => {
  it('sessizlik konuşma değil', () => {
    const features = frameFeatures(new Float32Array(1024));
    expect(isSpeechFrame(features, 0.012, 0.004, true)).toBe(false);
  });

  it('sesli sinüs konuşma', () => {
    const features = frameFeatures(sine(1024, 200));
    expect(features.zcr).toBeGreaterThan(0.004);
    expect(features.zcr).toBeLessThan(0.2);
    expect(isSpeechFrame(features, 0.012, 0.004, true)).toBe(true);
  });

  it('yüksek ZCR gürültüyü RMS’ten ayırır', () => {
    const features = frameFeatures(noise(1024, 0.4));
    expect(features.rms).toBeGreaterThan(0.3);
    expect(features.zcr).toBeGreaterThan(0.4);
    expect(isSpeechFrame(features, 0.012, 0.004, false)).toBe(false);
  });
});

describe('createEnergyZcrVad', () => {
  it('onSpeechStart / onAutoStop imzası aynı kalır', () => {
    let started = 0;
    let stopped = 0;
    let now = 0;
    const vad = createEnergyZcrVad({
      noiseThreshold: 0.012,
      silenceTimeoutMs: 200,
      initialSilenceTimeoutMs: 0,
      now: () => now,
      onSpeechStart: () => {
        started += 1;
      },
      onAutoStop: () => {
        stopped += 1;
      },
    });

    const voice = sine(1024, 180);
    for (let i = 0; i < 8; i += 1) vad.push(voice);
    expect(started).toBe(1);
    expect(vad.speechDetected).toBe(true);

    const quiet = new Float32Array(1024);
    now = 250;
    for (let i = 0; i < 3; i += 1) vad.push(quiet);
    expect(stopped).toBe(1);
  });

  it('konuşma yokken ilk sessizlik süresi dolunca durur', () => {
    let stopped = 0;
    let now = 0;
    const vad = createEnergyZcrVad({
      silenceTimeoutMs: 0,
      initialSilenceTimeoutMs: 400,
      now: () => now,
      onAutoStop: () => {
        stopped += 1;
      },
    });
    vad.push(new Float32Array(64));
    expect(stopped).toBe(0);
    now = 401;
    expect(vad.push(new Float32Array(64))).toBe('auto-stop');
    expect(stopped).toBe(1);
  });
});
