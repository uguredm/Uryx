/** Faz 5: ürün README no-code (git/npm ürün yolu değil). */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const repoRoot = resolve(__dirname, '../../..');

function quickStartSection(markdown: string, heading: string): string {
  const start = markdown.indexOf(heading);
  if (start < 0) return '';
  const rest = markdown.slice(start + heading.length);
  const next = rest.search(/\n## /);
  return next < 0 ? rest : rest.slice(0, next);
}

describe('ürün README no-code (Faz 5)', () => {
  it('README.md İngilizce hızlı başlangıçta git/npm/start-dev yok', () => {
    const readme = readFileSync(resolve(repoRoot, 'README.md'), 'utf8');
    expect(readme).toMatch(/\[Türkçe\]\(README\.tr\.md\)/i);
    const quick = quickStartSection(readme, '## Quick start');
    expect(quick.length).toBeGreaterThan(40);
    expect(quick).not.toMatch(/git clone/i);
    expect(quick).not.toMatch(/npm (install|run)/i);
    expect(quick).not.toMatch(/start-dev\.ps1/i);
  });

  it('README.tr.md aynı sırada git/npm/start-dev yok', () => {
    const readme = readFileSync(resolve(repoRoot, 'README.tr.md'), 'utf8');
    expect(readme).toMatch(/\[English\]\(README\.md\)/i);
    const quick = quickStartSection(readme, '## Hızlı başlangıç');
    expect(quick.length).toBeGreaterThan(40);
    expect(quick).not.toMatch(/git clone/i);
    expect(quick).not.toMatch(/npm (install|run)/i);
    expect(quick).not.toMatch(/start-dev\.ps1/i);
  });
});

describe('HANDOFF sanitizasyon (Faz 5.3)', () => {
  it('kişisel Users/Desktop yolu yok; şablon %USERPROFILE%', () => {
    const handoff = readFileSync(resolve(repoRoot, 'HANDOFF.md'), 'utf8');
    expect(handoff).toMatch(/%USERPROFILE%/);
    expect(handoff).not.toMatch(/[A-Za-z]:\\Users\\[A-Za-z]/i);
    expect(handoff).not.toMatch(/Desktop\\(?:Uryx_v2|Jarvis_v2)/i);
  });
});
