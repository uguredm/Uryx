/** openWakeWord host motoru — renderer ONNX yok; model yoksa Whisper yedeği. */

import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { DEFAULT_SETTINGS } from '@shared/settings';
import { IPC_INVOKE_CHANNELS } from '@shared/ipc';
import {
  MODELS_DIR_UI_HINT,
  ORT_PACKAGE,
  WAKE_EMBED_WINDOW,
  WAKE_FRAME_SAMPLES,
  WAKE_ONNX_FILES,
  classifyWakePcm,
  createOrtWakeInfer,
  createWakeOnnxEngine,
  loadOnnxRuntime,
  parseWakePcmPayload,
  pcmFloatToInt16Float,
  resampleTo16k,
  resolveWakeOnnxDir,
  squeezeMelFrames,
  wakeClipFrames,
  wakeModelsReady,
} from '../electron/wake-onnx';

describe('Faz 3.2 kilitleri', () => {
  it('wakeWordEnabled varsayılan kapalı', () => {
    expect(DEFAULT_SETTINGS.wakeWordEnabled).toBe(false);
  });

  it('UI ipucu ham C:\\Users yolu değil', () => {
    expect(MODELS_DIR_UI_HINT).toBe('%LOCALAPPDATA%\\Uryx\\models');
    expect(MODELS_DIR_UI_HINT.includes('C:\\Users')).toBe(false);
  });

  it('wake IPC whitelist’te; sınıflandırma main’de', () => {
    expect(IPC_INVOKE_CHANNELS).toContain('wake:status');
    expect(IPC_INVOKE_CHANNELS).toContain('wake:pushPcm');
  });
});

describe('wake onnx yolları', () => {
  const previous = process.env.LLM_MODELS_DIR;

  afterEach(() => {
    if (previous === undefined) delete process.env.LLM_MODELS_DIR;
    else process.env.LLM_MODELS_DIR = previous;
  });

  it('models/wake altında üç onnx bekler', () => {
    const root = join(process.env.URYX_TEST_ROOT!, 'wake-models');
    mkdirSync(root, { recursive: true });
    process.env.LLM_MODELS_DIR = root;
    const dir = resolveWakeOnnxDir();
    expect(dir.replace(/\\/g, '/').endsWith('/wake')).toBe(true);
    expect(WAKE_ONNX_FILES).toEqual(['melspectrogram.onnx', 'embedding.onnx', 'hey_uryx.onnx']);
    expect(wakeModelsReady(dir)).toBe(false);
  });

  it('dosyalar varsa hazır', () => {
    const dir = join(process.env.URYX_TEST_ROOT!, 'wake-ready', 'wake');
    mkdirSync(dir, { recursive: true });
    for (const name of WAKE_ONNX_FILES) writeFileSync(join(dir, name), 'x');
    expect(wakeModelsReady(dir)).toBe(true);
  });
});

describe('wakeClipFrames', () => {
  it('klibi 1280 örnek kareye böler, sondan 16 alır', () => {
    const frame = WAKE_FRAME_SAMPLES;
    const pcm = new Float32Array(frame * 18);
    for (let i = 0; i < 18; i += 1) pcm.fill(i + 1, i * frame, (i + 1) * frame);
    const frames = wakeClipFrames(pcm);
    expect(frames).toHaveLength(WAKE_EMBED_WINDOW);
    expect(frames[0][0]).toBe(3);
    expect(frames[15][0]).toBe(18);
  });

  it('kısa klip önden sıfır doldurur', () => {
    const pcm = new Float32Array(WAKE_FRAME_SAMPLES);
    pcm.fill(0.5);
    const frames = wakeClipFrames(pcm);
    expect(frames).toHaveLength(WAKE_EMBED_WINDOW);
    expect(frames[0].every((value) => value === 0)).toBe(true);
    expect(frames[15][0]).toBe(0.5);
  });
});

describe('openWakeWord ölçek', () => {
  it('PCM float int16 ölçeğine gider', () => {
    const scaled = pcmFloatToInt16Float(Float32Array.from([1, -1, 0, 0.5]));
    expect(scaled[0]).toBe(32767);
    expect(scaled[1]).toBe(-32767);
    expect(scaled[2]).toBe(0);
    expect(scaled[3]).toBe(16384);
  });

  it('mel çıktısını /10+2 ile 32 bin kareye sıkıştırır', () => {
    const data = new Float32Array(64);
    data.fill(0, 0, 32);
    data.fill(10, 32, 64);
    const frames = squeezeMelFrames(data);
    expect(frames).toHaveLength(2);
    expect(frames[0][0]).toBe(2);
    expect(frames[1][0]).toBe(3);
  });
});

describe('PCM', () => {
  it('16 kHz’e örnekler', () => {
    const src = Float32Array.from({ length: 48 }, (_, i) => (i % 2 === 0 ? 0.2 : -0.2));
    const out = resampleTo16k(src, 48_000);
    expect(out.length).toBe(16);
  });

  it('48 kHz bir saniyelik PCM kabul edilir', () => {
    const samples = Array.from({ length: 48_000 }, () => 0.1);
    const parsed = parseWakePcmPayload({ samples, sampleRate: 48_000 });
    expect(parsed.samples.length).toBe(48_000);
    expect(parsed.sampleRate).toBe(48_000);
  });

  it('uzun PCM atılmaz, kuyruk alınır', () => {
    const samples = Array.from({ length: 200_000 }, (_, i) => (i === 199_999 ? 0.7 : 0.1));
    const parsed = parseWakePcmPayload({ samples, sampleRate: 96_000 });
    expect(parsed.samples.length).toBeLessThanOrEqual(96_000);
    expect(parsed.samples[parsed.samples.length - 1]).toBeCloseTo(0.7);
  });

  it('sessizlik false-accept değil', async () => {
    const engine = createWakeOnnxEngine({
      infer: async () => 0.99,
      modelsReady: true,
    });
    const silence = new Float32Array(1600);
    const result = await classifyWakePcm(engine, silence, 16_000);
    expect(result.hit).toBe(false);
    expect(result.reason).toBe('silence');
  });

  it('eşik üstü skor uyandırır', async () => {
    const engine = createWakeOnnxEngine({
      infer: async () => 0.82,
      modelsReady: true,
    });
    const speech = Float32Array.from({ length: 1600 }, (_, i) => Math.sin(i / 8) * 0.4);
    const result = await classifyWakePcm(engine, speech, 16_000);
    expect(result.hit).toBe(true);
    expect(result.score).toBeGreaterThan(0.5);
  });

  it('dosya var ama infer yoksa Whisper yedeği', async () => {
    const engine = createWakeOnnxEngine({ modelsReady: true });
    expect(engine.usingFallback).toBe(true);
    const speech = Float32Array.from({ length: 1600 }, (_, i) => Math.sin(i / 8) * 0.4);
    const result = await classifyWakePcm(engine, speech, 16_000);
    expect(result.reason).toBe('fallback');
  });

  it('onnx yoksa yedek; çökmez', async () => {
    const engine = createWakeOnnxEngine({ modelsReady: false });
    const speech = Float32Array.from({ length: 1600 }, (_, i) => Math.sin(i / 8) * 0.4);
    const result = await classifyWakePcm(engine, speech, 16_000);
    expect(engine.usingFallback).toBe(true);
    expect(result.hit).toBe(false);
    expect(result.reason).toBe('fallback');
  });
});

describe('lazy onnxruntime-node', () => {
  it('paket adı onnxruntime-node; statik import yok', () => {
    expect(ORT_PACKAGE).toBe('onnxruntime-node');
    const src = readFileSync(join(__dirname, '../electron/wake-onnx.ts'), 'utf8');
    expect(src).not.toMatch(/from ['"]onnxruntime-node['"]/);
    expect(src).not.toMatch(/import\(['"]onnxruntime-node['"]\)/);
    const pkg = JSON.parse(readFileSync(join(__dirname, '../package.json'), 'utf8')) as {
      dependencies?: Record<string, string>;
      optionalDependencies?: Record<string, string>;
    };
    expect(
      pkg.optionalDependencies?.[ORT_PACKAGE] ?? pkg.dependencies?.[ORT_PACKAGE],
    ).toBeTruthy();
  });

  it('renderer ONNX paketi içermez', () => {
    const root = join(__dirname, '../src');
    const stack = [root];
    while (stack.length) {
      const dir = stack.pop()!;
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          stack.push(full);
          continue;
        }
        if (!full.endsWith('.ts') && !full.endsWith('.tsx')) continue;
        expect(readFileSync(full, 'utf8')).not.toMatch(/onnxruntime/);
      }
    }
  });

  it('yükleyici hata verirse null döner', async () => {
    await expect(
      loadOnnxRuntime(async () => {
        throw new Error('native missing');
      }),
    ).resolves.toBeNull();
  });

  it('üç oturumu zincirler ve skoru üretir', async () => {
    const dir = join(process.env.URYX_TEST_ROOT!, 'wake-ort', 'wake');
    mkdirSync(dir, { recursive: true });
    for (const name of WAKE_ONNX_FILES) writeFileSync(join(dir, name), 'x');

    const created: string[] = [];
    const infer = await createOrtWakeInfer({
      dir,
      importOrt: async () => fakeOrt(0.77, created),
    });
    expect(infer).toBeDefined();
    expect(created).toEqual([...WAKE_ONNX_FILES]);
    const speech = Float32Array.from({ length: 1600 }, (_, i) => Math.sin(i / 8) * 0.4);
    expect(await infer!(speech)).toBeCloseTo(0.77);

    const engine = createWakeOnnxEngine({ infer, modelsReady: true });
    expect(engine.usingFallback).toBe(false);
    const result = await classifyWakePcm(engine, speech, 16_000);
    expect(result.hit).toBe(true);
  });

  it('infer her çağrıda klibi baştan kareler; önceki miss sızmaz', async () => {
    const dir = join(process.env.URYX_TEST_ROOT!, 'wake-ort-reset', 'wake');
    mkdirSync(dir, { recursive: true });
    for (const name of WAKE_ONNX_FILES) writeFileSync(join(dir, name), 'x');
    const embeddingCalls: number[] = [];
    let current = 0;
    const infer = await createOrtWakeInfer({
      dir,
      importOrt: async () =>
        fakeOrt(0.77, [], {
          onEmbedding: () => {
            current += 1;
          },
          onClassifier: () => {
            embeddingCalls.push(current);
            current = 0;
          },
        }),
    });
    expect(infer).toBeDefined();
    const oneSecond = Float32Array.from({ length: 16_000 }, (_, i) => Math.sin(i / 8) * 0.4);
    await infer!(oneSecond);
    await infer!(oneSecond);
    expect(embeddingCalls).toHaveLength(2);
    expect(embeddingCalls[0]).toBe(embeddingCalls[1]);
    expect(embeddingCalls[0]).toBeGreaterThan(0);
  });

  it('ORT yoksa infer bağlanmaz', async () => {
    const dir = join(process.env.URYX_TEST_ROOT!, 'wake-ort-miss', 'wake');
    mkdirSync(dir, { recursive: true });
    for (const name of WAKE_ONNX_FILES) writeFileSync(join(dir, name), 'x');
    const infer = await createOrtWakeInfer({
      dir,
      importOrt: async () => {
        throw new Error('no native');
      },
    });
    expect(infer).toBeUndefined();
  });
});

class FakeTensor {
  constructor(
    public type: string,
    public data: Float32Array,
    public dims: number[],
  ) {}
}

function fakeOrt(
  score: number,
  created: string[],
  hooks: { onEmbedding?: () => void; onClassifier?: () => void } = {},
) {
  return {
    Tensor: FakeTensor,
    InferenceSession: {
      create: async (modelPath: string) => {
        const file = modelPath.replace(/\\/g, '/').split('/').pop() ?? modelPath;
        created.push(file);
        return {
          inputNames: ['input'],
          outputNames: ['output'],
          run: async () => {
            if (file === 'embedding.onnx') hooks.onEmbedding?.();
            if (file === 'hey_uryx.onnx') hooks.onClassifier?.();
            return {
              output: new FakeTensor(
                'float32',
                file === 'hey_uryx.onnx' ? Float32Array.from([score]) : new Float32Array(96),
                file === 'hey_uryx.onnx' ? [1] : [1, 96],
              ),
            };
          },
        };
      },
    },
  };
}
