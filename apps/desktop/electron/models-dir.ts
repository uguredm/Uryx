/**
 * Ortak GGUF kökü — installer ve geliştirme aynı dizini kullanır.
 * `%LOCALAPPDATA%\Uryx\models` (testte URYX_TEST_ROOT).
 */

import { app } from 'electron';
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import { LLM_PRESETS, resolveLlmPreset, type LlmPreset } from '@shared/settings';

function isTestProcess(): boolean {
  return Boolean(process.env.VITEST || process.env.URYX_TEST_ROOT);
}

/** Host’taki kanonik GGUF klasörü. */
export function resolveModelsDir(): string {
  const fromEnv = (process.env.LLM_MODELS_DIR ?? '').trim();
  if (fromEnv) return path.resolve(fromEnv);
  if (isTestProcess()) {
    const root = process.env.URYX_TEST_ROOT || app.getPath('userData');
    return path.join(root, 'Uryx', 'models');
  }
  const local = process.env.LOCALAPPDATA || path.join(app.getPath('appData'), '..', 'Local');
  return path.join(local, 'Uryx', 'models');
}

export function ensureModelsDir(): string {
  const dir = resolveModelsDir();
  mkdirSync(dir, { recursive: true });
  return dir;
}

/** Docker Compose Windows yolunu eğik çizgiyle bekler. */
export function posixModelsDir(dir = ensureModelsDir()): string {
  return dir.replace(/\\/g, '/');
}

export function listGgufFiles(dir = ensureModelsDir()): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).filter((name) => name.toLowerCase().endsWith('.gguf'));
}

function copyMissingGgufs(source: string, dest: string): void {
  if (!existsSync(source) || path.resolve(source) === path.resolve(dest)) return;
  for (const name of readdirSync(source)) {
    if (!name.toLowerCase().endsWith('.gguf')) continue;
    const target = path.join(dest, name);
    if (existsSync(target)) continue;
    copyFileSync(path.join(source, name), target);
  }
}

/** Repo / eski installer `models/` altındaki GGUF’ları kullanıcı dizinine taşır. */
export function migrateRepoGgufs(repoRoot: string | null): string {
  const dest = ensureModelsDir();
  if (repoRoot) copyMissingGgufs(path.join(repoRoot, 'models'), dest);
  return dest;
}

function upsertEnvKey(text: string, key: string, value: string): string {
  const line = `${key}=${value}`;
  const pattern = new RegExp(`^${key}=.*$`, 'm');
  if (pattern.test(text)) return text.replace(pattern, line);
  const trimmed = text.replace(/\s+$/, '');
  return `${trimmed}${trimmed ? '\n' : ''}${line}\n`;
}

export function applyLlmComposeEnv(
  repoRoot: string,
  preset: LlmPreset,
  modelName?: string,
): void {
  const spec = LLM_PRESETS[preset];
  const modelsDir = posixModelsDir();
  const envPath = path.join(repoRoot, '.env');
  let text = existsSync(envPath) ? readFileSync(envPath, 'utf8') : '';
  text = upsertEnvKey(text, 'LLM_MODELS_DIR', modelsDir);
  text = upsertEnvKey(text, 'LLM_MODEL', modelName?.trim() || spec.modelName);
  text = upsertEnvKey(text, 'LLM_GGUF_FILE', spec.ggufFile);
  try {
    writeFileSync(envPath, text, 'utf8');
  } catch {
  }
  process.env.LLM_MODELS_DIR = modelsDir;
  process.env.LLM_MODEL = modelName?.trim() || spec.modelName;
  process.env.LLM_GGUF_FILE = spec.ggufFile;
}

export function bindProcessModelsDir(): string {
  const dir = posixModelsDir();
  process.env.LLM_MODELS_DIR = dir;
  return dir;
}

export function presetFromSettings(modelName: string, preset?: string | null): LlmPreset {
  return resolveLlmPreset(modelName, preset);
}
