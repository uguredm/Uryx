import { describe, expect, it } from 'vitest';

import { classifyIdleWake, extractWakeCommand, wakePcmWindow } from '@/lib/wakeWord';

describe('extractWakeCommand', () => {
  it('uyandırma ifadesinden sonraki komutu çıkarır', () => {
    expect(extractWakeCommand('Hey Uryx, dün çıkan filmleri araştır.', 'uryx')).toBe(
      'dün çıkan filmleri araştır.',
    );
  });

  it('yalnızca uyandırma söylendiyse boş komut döndürür', () => {
    expect(extractWakeCommand('Hey Uryx!', 'uryx')).toBe('');
  });

  it('Whisper telaffuz varyasyonlarını kabul eder', () => {
    expect(extractWakeCommand('Hey Carvis nasılsın?', 'uryx')).toBe('nasılsın?');
    expect(extractWakeCommand('Hey Larvis nasılsın?', 'uryx')).toBe('nasılsın?');
    expect(extractWakeCommand('Cervis', 'uryx')).toBe('');
  });

  it('doğal alternatif uyandırma ifadelerini kabul eder', () => {
    expect(extractWakeCommand('Uyan', 'uryx')).toBe('');
    expect(extractWakeCommand('Uryx uyan', 'uryx')).toBe('');
    expect(extractWakeCommand('Uyan Uryx hava nasıl?', 'uryx')).toBe('hava nasıl?');
    expect(extractWakeCommand('Dinle Uryx, müzik aç', 'uryx')).toBe('müzik aç');
    expect(extractWakeCommand('Baksana saat kaç?', 'uryx')).toBe('saat kaç?');
  });

  it('normal konuşmayı uyandırma olarak kabul etmez', () => {
    expect(extractWakeCommand('Bugün Uryx hakkında konuşalım', 'uryx')).toBeNull();
    expect(extractWakeCommand('Merhaba nasılsın?', 'uryx')).toBeNull();
  });
});

describe('classifyIdleWake', () => {
  const speech = Float32Array.from({ length: 1600 }, (_, i) => Math.sin(i / 8) * 0.4);

  it('host ONNX vuruşunda Whisper yedeğine düşmez', async () => {
    let pushed = false;
    const decision = await classifyIdleWake({
      host: {
        status: async () => ({ usingFallback: false }),
        pushPcm: async () => {
          pushed = true;
          return { hit: true, score: 0.82, reason: 'hit' };
        },
      },
      samples: speech,
      sampleRate: 16_000,
    });
    expect(decision).toBe('onnx_hit');
    expect(pushed).toBe(true);
  });

  it('ONNX kaçırınca Whisper çağırmaz', async () => {
    const decision = await classifyIdleWake({
      host: {
        status: async () => ({ usingFallback: false }),
        pushPcm: async () => ({ hit: false, score: 0.1, reason: 'low_score' }),
      },
      samples: speech,
      sampleRate: 16_000,
    });
    expect(decision).toBe('onnx_miss');
  });

  it('model yoksa Whisper yedeğine düşer', async () => {
    const decision = await classifyIdleWake({
      host: {
        status: async () => ({ usingFallback: true }),
        pushPcm: async () => {
          throw new Error('fallback PCM gitmemeli');
        },
      },
      samples: speech,
      sampleRate: 16_000,
    });
    expect(decision).toBe('whisper_fallback');
  });

  it('host yoksa Whisper yedeğine düşer', async () => {
    const decision = await classifyIdleWake({
      samples: speech,
      sampleRate: 16_000,
    });
    expect(decision).toBe('whisper_fallback');
  });

  it('IPC öncesi 16 kHz kuyruk gönderir; uzun klip hata değil', async () => {
    let received = { n: 0, rate: 0 };
    const decision = await classifyIdleWake({
      host: {
        status: async () => ({ usingFallback: false }),
        pushPcm: async (samples, sampleRate) => {
          received = { n: samples.length, rate: sampleRate };
          return { hit: false, score: 0.1, reason: 'low_score' };
        },
      },
      samples: Float32Array.from({ length: 144_000 }, () => 0.2),
      sampleRate: 96_000,
    });
    expect(decision).toBe('onnx_miss');
    expect(received.rate).toBe(16_000);
    expect(received.n).toBeLessThanOrEqual(16_000 * 2);
    expect(received.n).toBeGreaterThan(0);
  });

  it('pushPcm hata verirse Whisper yedeğine düşer', async () => {
    const decision = await classifyIdleWake({
      host: {
        status: async () => ({ usingFallback: false }),
        pushPcm: async () => {
          throw new Error('wake pcm çok uzun');
        },
      },
      samples: speech,
      sampleRate: 16_000,
    });
    expect(decision).toBe('whisper_fallback');
  });
});

describe('wakePcmWindow', () => {
  it('yalnız son pencereyi tutar', () => {
    const samples = Float32Array.from({ length: 100 }, (_, i) => i);
    const window = wakePcmWindow(samples, 100, 0.5);
    expect(Array.from(window)).toEqual(Array.from({ length: 50 }, (_, i) => i + 50));
  });
});
