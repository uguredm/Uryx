/** Odysseus `_safe_url` + Sentry query/userinfo strip. */

import { describe, expect, it } from 'vitest';

import { formatComposeConfigFailure } from '../electron/services-health';
import { truncateHostResult } from '../electron/host-tools/guard';
import { redactHostText, redactSecretsInText, redactUrlsInText, safeUrl } from '../electron/host-tools/safe-url';

describe('Odysseus _safe_url', () => {
  it('userinfo ve query/fragment düşer, host+path kalır', () => {
    expect(safeUrl('https://user:ghp_secret@ghcr.io/v2/foo?scope=pull#x')).toBe(
      'https://ghcr.io/v2/foo',
    );
    expect(safeUrl('ws://127.0.0.1:8080/ws/host?token=super-secret')).toBe(
      'ws://127.0.0.1:8080/ws/host',
    );
    expect(safeUrl('http://192.168.1.10:2375')).toBe('http://192.168.1.10:2375');
  });

  it('log satırındaki registry URL’sinden token’ı siler', () => {
    const text = redactUrlsInText(
      'Get "https://user:pat@ghcr.io/v2/uryx/manifests/latest?scope=repository": unauthorized',
    );
    expect(text).toContain('https://ghcr.io/v2/uryx/manifests/latest');
    expect(text).not.toMatch(/pat|scope=repository/i);
  });
});

describe('MCP / host sır süzgeci', () => {
  it('PAT, Bearer ve env=değer düşer, URL userinfo durur', () => {
    expect(redactSecretsInText('token ghp_abcdefghij extra')).toBe('token [redacted] extra');
    expect(redactSecretsInText('Authorization: Bearer abcdefghijk')).toMatch(/\[redacted\]/);
    expect(redactSecretsInText('CONTEXT7_API_KEY=ctx7sk_usersecret')).not.toMatch(/ctx7sk_usersecret/);
    const mixed = redactHostText(
      'fail https://user:ghp_leakpath@ghcr.io/pkg?token=abc Bearer ghp_leakplain99',
    );
    expect(mixed).toContain('https://ghcr.io/pkg');
    expect(mixed).not.toMatch(/ghp_leakpath|ghp_leakplain99|token=abc/i);
  });
});

describe('host çıktı süzgeci', () => {
  it('truncateHostResult kısa logdaki query’yi de siler', () => {
    const { result } = truncateHostResult({
      text: 'çekildi https://index.docker.io/v1/?account=ugur&token=abc',
    });
    expect(String(result.text)).toContain('https://index.docker.io/v1');
    expect(String(result.text)).not.toMatch(/token=abc|account=ugur/);
  });

  it('truncateHostResult MCP stderr PAT’ını düşürür', () => {
    const { result } = truncateHostResult({
      text: 'npx fail GITHUB_PERSONAL_ACCESS_TOKEN=gho_leakfromlog99',
    });
    expect(String(result.text)).not.toMatch(/gho_leakfromlog99/);
    expect(String(result.text)).toContain('[redacted]');
  });

  it('compose config hatasındaki URL’yi temizler', () => {
    const message = formatComposeConfigFailure(
      1,
      '',
      'pull failed: https://user:pass@registry.example/v2/foo?n=1',
      'tr',
    );
    expect(message).toMatch(/geçersiz/i);
    expect(message).toContain('https://registry.example/v2/foo');
    expect(message).not.toMatch(/user:pass|n=1/);
  });
});
