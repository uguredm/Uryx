/**
 * openWakeWord — Electron main. Renderer'da ONNX yok. Docker yok.
 *
 * Model üçlüsü ``%LOCALAPPDATA%\\Uryx\\models\\wake``:
 * melspectrogram.onnx, embedding.onnx, hey_uryx.onnx
 * Yoksa Whisper + extractWakeCommand yedeği (usingFallback).
 */

import { existsSync } from 'node:fs';
import path from 'node:path';

import { hostText } from './host-i18n';
import { resolveModelsDir } from './models-dir';

export const MODELS_DIR_UI_HINT = '%LOCALAPPDATA%\\Uryx\\models';

export const WAKE_ONNX_FILES = ['melspectrogram.onnx', 'embedding.onnx', 'hey_uryx.onnx'] as const;

export const WAKE_SCORE_THRESHOLD = 0.5;
export const WAKE_SILENCE_RMS = 0.02;
export const WAKE_SAMPLE_RATE = 16_000;
/** Renderer 48–96 kHz gönderebilir; tavan 2 sn @ 48 kHz. Fazlası kuyruk. */
export const MAX_PCM_SAMPLES = 48_000 * 2;
export const ORT_PACKAGE = 'onnxruntime-node';
export const WAKE_FRAME_SAMPLES = 1280;
export const WAKE_EMBED_WINDOW = 16;
export const WAKE_MEL_WINDOW = 76;
export const WAKE_MEL_HOP = 8;
export const WAKE_MEL_BINS = 32;
export const WAKE_EMBED_DIM = 96;
const INT16_PEAK = 32_767;

export type WakeHitReason = 'hit' | 'low_score' | 'silence' | 'fallback' | 'empty';

export interface WakeClassifyResult {
  hit: boolean;
  score: number;
  reason: WakeHitReason;
}

export interface WakeEngineStatus {
  engine: 'onnx' | 'whisper_fallback';
  modelPresent: boolean;
  modelsHint: string;
  usingFallback: boolean;
}

export interface WakeInferHooks {
  infer?: (pcm16k: Float32Array) => Promise<number>;
  modelsReady?: boolean;
}

export interface OrtTensor {
  data: ArrayLike<number>;
  dims?: readonly number[];
}

export interface OrtSession {
  inputNames: readonly string[];
  outputNames: readonly string[];
  run: (feeds: Record<string, OrtTensor>) => Promise<Record<string, OrtTensor>>;
}

export interface OrtLike {
  Tensor: new (type: string, data: Float32Array, dims: number[]) => OrtTensor;
  InferenceSession: {
    create: (modelPath: string) => Promise<OrtSession>;
  };
}

export interface WakeOnnxEngine {
  usingFallback: boolean;
  infer?: (pcm16k: Float32Array) => Promise<number>;
  status: () => WakeEngineStatus;
}

export function resolveWakeOnnxDir(modelsDir = resolveModelsDir()): string {
  return path.join(modelsDir, 'wake');
}

export function wakeModelsReady(dir: string): boolean {
  return WAKE_ONNX_FILES.every((name) => existsSync(path.join(dir, name)));
}

export function resampleTo16k(samples: Float32Array, sampleRate: number): Float32Array {
  if (samples.length === 0) return new Float32Array(0);
  const rate = sampleRate > 0 ? sampleRate : WAKE_SAMPLE_RATE;
  if (rate === WAKE_SAMPLE_RATE) return Float32Array.from(samples);
  const outLength = Math.max(1, Math.floor((samples.length * WAKE_SAMPLE_RATE) / rate));
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

function rms(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const value of samples) sum += value * value;
  return Math.sqrt(sum / samples.length);
}

export function createWakeOnnxEngine(hooks: WakeInferHooks = {}): WakeOnnxEngine {
  const present = hooks.modelsReady ?? wakeModelsReady(resolveWakeOnnxDir());
  const usingFallback = !present || !hooks.infer;
  return {
    usingFallback,
    infer: hooks.infer,
    status: () => ({
      engine: usingFallback ? 'whisper_fallback' : 'onnx',
      modelPresent: present,
      modelsHint: MODELS_DIR_UI_HINT,
      usingFallback,
    }),
  };
}

export async function loadOnnxRuntime(importOrt?: () => Promise<OrtLike>): Promise<OrtLike | null> {
  try {
    const loaded = await (importOrt ?? defaultImportOrt)();
    if (!loaded?.InferenceSession?.create) return null;
    return loaded;
  } catch {
    return null;
  }
}

async function defaultImportOrt(): Promise<OrtLike> {
  const { createRequire } = await import('node:module');
  const require = createRequire(import.meta.url);
  return require(ORT_PACKAGE) as OrtLike;
}

function firstOutput(result: Record<string, OrtTensor>, session: OrtSession): OrtTensor {
  const name = session.outputNames[0] ?? Object.keys(result)[0];
  return result[name] ?? { data: new Float32Array(0) };
}

export function pcmFloatToInt16Float(pcm: Float32Array): Float32Array {
  const out = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i += 1) {
    const clipped = Math.max(-1, Math.min(1, pcm[i]));
    out[i] = Math.round(clipped * INT16_PEAK);
  }
  return out;
}

export function squeezeMelFrames(data: ArrayLike<number>): Float32Array[] {
  const arr = Float32Array.from(data as number[]);
  const n = Math.floor(arr.length / WAKE_MEL_BINS);
  const frames: Float32Array[] = [];
  for (let i = 0; i < n; i += 1) {
    const row = new Float32Array(WAKE_MEL_BINS);
    for (let j = 0; j < WAKE_MEL_BINS; j += 1) {
      row[j] = arr[i * WAKE_MEL_BINS + j] / 10 + 2;
    }
    frames.push(row);
  }
  return frames;
}

function padMelOnes(frames: Float32Array[]): Float32Array[] {
  if (frames.length >= WAKE_MEL_WINDOW) return frames;
  const pad: Float32Array[] = [];
  while (pad.length + frames.length < WAKE_MEL_WINDOW) {
    pad.push(new Float32Array(WAKE_MEL_BINS).fill(1));
  }
  return pad.concat(frames);
}

function melWindows(frames: Float32Array[]): Float32Array[] {
  const padded = padMelOnes(frames);
  const windows: Float32Array[] = [];
  for (let i = 0; i + WAKE_MEL_WINDOW <= padded.length; i += WAKE_MEL_HOP) {
    const stacked = new Float32Array(WAKE_MEL_WINDOW * WAKE_MEL_BINS);
    for (let t = 0; t < WAKE_MEL_WINDOW; t += 1) stacked.set(padded[i + t], t * WAKE_MEL_BINS);
    windows.push(stacked);
  }
  if (windows.length === 0 && padded.length >= WAKE_MEL_WINDOW) {
    const stacked = new Float32Array(WAKE_MEL_WINDOW * WAKE_MEL_BINS);
    for (let t = 0; t < WAKE_MEL_WINDOW; t += 1) stacked.set(padded[t], t * WAKE_MEL_BINS);
    windows.push(stacked);
  }
  return windows;
}

export function wakeClipFrames(
  pcm16k: Float32Array,
  frame = WAKE_FRAME_SAMPLES,
  window = WAKE_EMBED_WINDOW,
): Float32Array[] {
  const frames: Float32Array[] = [];
  if (frame <= 0 || window <= 0) return frames;
  let end = pcm16k.length;
  while (frames.length < window && end > 0) {
    const start = Math.max(0, end - frame);
    const chunk = new Float32Array(frame);
    const span = end - start;
    if (span > 0) chunk.set(pcm16k.subarray(start, end), frame - span);
    frames.unshift(chunk);
    end = start;
  }
  while (frames.length < window) frames.unshift(new Float32Array(frame));
  return frames;
}

function padOrTrim(vec: Float32Array, dim: number): Float32Array {
  if (vec.length === dim) return vec;
  const out = new Float32Array(dim);
  out.set(vec.subarray(0, Math.min(vec.length, dim)));
  return out;
}

function makeOrtInfer(ort: OrtLike, sessions: OrtSession[]): (pcm16k: Float32Array) => Promise<number> {
  const [mel, embedding, classifier] = sessions;
  let embedDim = WAKE_EMBED_DIM;

  return async (pcm16k: Float32Array): Promise<number> => {
    try {
      const scaled = pcmFloatToInt16Float(pcm16k);
      const melOut = firstOutput(
        await mel.run({
          [mel.inputNames[0] ?? 'input']: new ort.Tensor('float32', scaled, [1, scaled.length]),
        }),
        mel,
      );
      const windows = melWindows(squeezeMelFrames(melOut.data));
      const embeddings: Float32Array[] = [];
      for (const window of windows) {
        const embOut = firstOutput(
          await embedding.run({
            [embedding.inputNames[0] ?? 'input_1']: new ort.Tensor('float32', window, [
              1,
              WAKE_MEL_WINDOW,
              WAKE_MEL_BINS,
              1,
            ]),
          }),
          embedding,
        );
        const vec = Float32Array.from(embOut.data);
        if (vec.length) embedDim = vec.length;
        embeddings.push(padOrTrim(vec, embedDim));
      }
      const taken = embeddings.slice(-WAKE_EMBED_WINDOW);
      while (taken.length < WAKE_EMBED_WINDOW) taken.unshift(new Float32Array(embedDim));
      const stacked = new Float32Array(WAKE_EMBED_WINDOW * embedDim);
      taken.forEach((row, index) => stacked.set(padOrTrim(row, embedDim), index * embedDim));
      const scoreOut = firstOutput(
        await classifier.run({
          [classifier.inputNames[0] ?? 'input']: new ort.Tensor('float32', stacked, [
            1,
            WAKE_EMBED_WINDOW,
            embedDim,
          ]),
        }),
        classifier,
      );
      let best = 0;
      for (let i = 0; i < scoreOut.data.length; i += 1) {
        const value = Number(scoreOut.data[i]);
        if (Number.isFinite(value) && value > best) best = value;
      }
      return best;
    } catch {
      return 0;
    }
  };
}

export async function createOrtWakeInfer(opts: {
  dir?: string;
  importOrt?: () => Promise<OrtLike>;
} = {}): Promise<((pcm16k: Float32Array) => Promise<number>) | undefined> {
  const dir = opts.dir ?? resolveWakeOnnxDir();
  if (!wakeModelsReady(dir)) return undefined;
  const ort = await loadOnnxRuntime(opts.importOrt);
  if (!ort) return undefined;
  try {
    const sessions: OrtSession[] = [];
    for (const name of WAKE_ONNX_FILES) {
      sessions.push(await ort.InferenceSession.create(path.join(dir, name)));
    }
    if (sessions.length !== WAKE_ONNX_FILES.length) return undefined;
    return makeOrtInfer(ort, sessions);
  } catch {
    return undefined;
  }
}

export async function classifyWakePcm(
  engine: WakeOnnxEngine,
  samples: ArrayLike<number>,
  sampleRate: number,
): Promise<WakeClassifyResult> {
  const pcm = samples instanceof Float32Array ? samples : Float32Array.from(samples as number[]);
  if (pcm.length === 0) return { hit: false, score: 0, reason: 'empty' };
  if (engine.usingFallback && !engine.infer) {
    return { hit: false, score: 0, reason: 'fallback' };
  }
  const pcm16 = resampleTo16k(pcm, sampleRate);
  if (rms(pcm16) < WAKE_SILENCE_RMS) {
    return { hit: false, score: 0, reason: 'silence' };
  }
  if (!engine.infer) {
    return { hit: false, score: 0, reason: 'fallback' };
  }
  const score = await engine.infer(pcm16);
  if (score >= WAKE_SCORE_THRESHOLD) return { hit: true, score, reason: 'hit' };
  return { hit: false, score, reason: 'low_score' };
}

export function parseWakePcmPayload(payload: unknown): { samples: Float32Array; sampleRate: number } {
  const body = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  const raw = body.samples;
  const sampleRate = Number(body.sampleRate);
  if (!Array.isArray(raw)) {
    throw new Error(hostText('wake pcm geçersiz', 'wake pcm is invalid'));
  }
  const rate = sampleRate > 0 ? sampleRate : WAKE_SAMPLE_RATE;
  const maxKeep = Math.max(1, Math.min(MAX_PCM_SAMPLES, Math.floor(rate * 2)));
  const start = Math.max(0, raw.length - maxKeep);
  const slice = raw.slice(start);
  const samples = new Float32Array(slice.length);
  for (let i = 0; i < slice.length; i += 1) {
    const value = Number(slice[i]);
    samples[i] = Number.isFinite(value) ? Math.max(-1, Math.min(1, value)) : 0;
  }
  return {
    samples,
    sampleRate: rate,
  };
}

let ipcEngine = createWakeOnnxEngine();
let ortTried = false;

export function resetWakeOnnxForTests(hooks: WakeInferHooks = {}): void {
  ipcEngine = createWakeOnnxEngine(hooks);
  ortTried = false;
}

export async function ensureIpcWakeEngine(): Promise<WakeOnnxEngine> {
  if (!ipcEngine.usingFallback || ortTried) return ipcEngine;
  ortTried = true;
  const infer = await createOrtWakeInfer();
  if (infer) ipcEngine = createWakeOnnxEngine({ infer, modelsReady: true });
  return ipcEngine;
}

export async function wakeStatusForIpc(): Promise<WakeEngineStatus> {
  await ensureIpcWakeEngine();
  return ipcEngine.status();
}

export async function wakePushPcmForIpc(payload: unknown): Promise<WakeClassifyResult> {
  const { samples, sampleRate } = parseWakePcmPayload(payload);
  await ensureIpcWakeEngine();
  return classifyWakePcm(ipcEngine, samples, sampleRate);
}
