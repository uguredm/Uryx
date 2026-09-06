/** Güncelleme kanalı: public dene, gerekirse gizli + token. */

import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  classifyUpdaterError,
  nextUpdaterFeed,
  productSafeUpdaterMessage,
  updaterStartDecision,
} from '../electron/updater-gate';

const desktopRoot = join(dirname(fileURLToPath(import.meta.url)), '..');

describe('updaterStartDecision', () => {
  it('paketli uygulamada güncelleme kontrolü başlar', () => {
    expect(updaterStartDecision(true)).toBe('start');
  });

  it('geliştirme modunda güncelleme aramaz', () => {
    expect(updaterStartDecision(false)).toBe('unpackaged');
  });
});

describe('güncelleme kanalı sözleşmesi', () => {
  it('ilk deneme her zaman public latest.yml (token şart değil)', () => {
    expect(nextUpdaterFeed({ current: null, hasToken: false, error: null })).toBe('public');
    expect(nextUpdaterFeed({ current: null, hasToken: true, error: null })).toBe('public');
  });

  it('public 404/401 ve token varsa gizli kanala düşer', () => {
    expect(
      nextUpdaterFeed({
        current: 'public',
        hasToken: true,
        error: 'Cannot find latest.yml in the latest release artifacts 404',
      }),
    ).toBe('private');
    expect(
      nextUpdaterFeed({
        current: 'public',
        hasToken: true,
        error: '401 Unauthorized',
      }),
    ).toBe('private');
  });

  it('token yokken public 404 sonrası kanal değiştirmez', () => {
    expect(
      nextUpdaterFeed({
        current: 'public',
        hasToken: false,
        error: '404 not found',
      }),
    ).toBe('give-up');
  });

  it('gizli kanal da kırılırsa tekrar public’e dönmez (döngü yok)', () => {
    expect(
      nextUpdaterFeed({
        current: 'private',
        hasToken: true,
        error: '404',
      }),
    ).toBe('give-up');
  });

  it('ağ hatasında kanal değiştirmez', () => {
    expect(classifyUpdaterError('net::ERR_TIMED_OUT')).toBe('network');
    expect(
      nextUpdaterFeed({
        current: 'public',
        hasToken: true,
        error: 'net::ERR_TIMED_OUT',
      }),
    ).toBe('give-up');
  });
});

describe('yayın sözleşmesi (kırma)', () => {
  it('appId ve NSIS artifact adı sabit kalır', () => {
    const yml = readFileSync(join(desktopRoot, 'electron-builder.yml'), 'utf8');
    expect(yml).toMatch(/^appId:\s*com\.uryx\.desktop\s*$/m);
    expect(yml).toMatch(/artifactName:\s*Uryx-Setup\.\$\{ext\}/);
    expect(yml).toMatch(/releaseType:\s*release/);
    expect(yml).toMatch(/repo:\s*Uryx/);
    expect(yml).toMatch(/private:\s*true/);
  });

  it('istemci önce public Uryx, yedek gizli uryx-test', () => {
    const updater = readFileSync(join(desktopRoot, 'electron', 'updater.ts'), 'utf8');
    expect(updater).toMatch(/repo: 'Uryx'/);
    expect(updater).toMatch(/repo: 'uryx-test'/);
    expect(updater).toMatch(/private: false/);
  });

  it('ürün güncelleme metni gh auth demez', () => {
    expect(
      productSafeUpdaterMessage({ kind: 'auth', feed: 'private' }).toLowerCase(),
    ).not.toMatch(/gh auth/);
    expect(productSafeUpdaterMessage({ kind: 'not-found', feed: 'public' }).toLowerCase()).not.toMatch(
      /gizli github/,
    );
  });

  it('publish scripti exe + sha256 + blockmap + latest.yml ister', () => {
    const script = readFileSync(
      join(desktopRoot, '..', '..', 'scripts', 'publish-github-release.ps1'),
      'utf8',
    );
    expect(script).toContain('Uryx-Setup.exe');
    expect(script).toContain('Uryx-Setup.exe.sha256');
    expect(script).toContain('Uryx-Setup.exe.blockmap');
    expect(script).toContain('latest.yml');
    expect(script).toContain("path:\\s*Uryx-Setup\\.exe");
  });
});
