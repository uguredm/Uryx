import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const repoRoot = resolve(__dirname, '../../..');

describe('shared-types semver (Faz 4.5)', () => {
  it('0.1.0 kalır; README sözleşme paketinin uygulama semverinden bağımsız olduğunu söyler', () => {
    const pkg = JSON.parse(
      readFileSync(resolve(repoRoot, 'packages/shared-types/package.json'), 'utf8'),
    ) as { version: string };
    expect(pkg.version).toBe('0.1.0');

    const readme = readFileSync(resolve(repoRoot, 'README.md'), 'utf8');
    const contributing = readFileSync(resolve(repoRoot, 'CONTRIBUTING.md'), 'utf8');
    expect(`${readme}\n${contributing}`).toMatch(/sözleşme paketi bağımsız/i);
  });
});
