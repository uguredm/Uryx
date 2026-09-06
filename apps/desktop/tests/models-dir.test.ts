/** Ortak GGUF kökü. */

import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { listGgufFiles, posixModelsDir, resolveModelsDir } from '../electron/models-dir';

describe('models-dir', () => {
  const previous = process.env.LLM_MODELS_DIR;

  afterEach(() => {
    if (previous === undefined) delete process.env.LLM_MODELS_DIR;
    else process.env.LLM_MODELS_DIR = previous;
  });

  it('LLM_MODELS_DIR ortamını kullanır', () => {
    const dir = join(process.env.URYX_TEST_ROOT!, 'custom-models');
    mkdirSync(dir, { recursive: true });
    process.env.LLM_MODELS_DIR = dir;
    expect(resolveModelsDir()).toBe(dir);
    expect(posixModelsDir(dir).includes('\\')).toBe(false);
  });

  it('GGUF dosyalarını listeler', () => {
    const dir = join(process.env.URYX_TEST_ROOT!, 'gguf-list');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'Qwen3-1.7B-Q4_K_M.gguf'), 'x');
    writeFileSync(join(dir, 'Qwen3-8B-Q4_K_M.gguf'), 'x');
    writeFileSync(join(dir, 'README.md'), 'no');
    expect(listGgufFiles(dir).sort()).toEqual(
      ['Qwen3-1.7B-Q4_K_M.gguf', 'Qwen3-8B-Q4_K_M.gguf'].sort(),
    );
  });
});
