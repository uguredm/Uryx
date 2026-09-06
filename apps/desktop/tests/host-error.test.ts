/** Odysseus `_classify_error` + Undici kodları — str(exc) yok. */

import { describe, expect, it } from 'vitest';

import { classifyHostError, formatHostError } from '../electron/host-tools/host-error';

describe('Odysseus host error class', () => {
  it('ECONNREFUSED / Undici timeout sınıflar, metni sızdırmaz', () => {
    const refused = Object.assign(new Error('connect ECONNREFUSED 127.0.0.1:2375'), {
      code: 'ECONNREFUSED',
    });
    expect(classifyHostError(refused)).toBe('connection_refused');
    expect(formatHostError(refused)).toBe('Bağlantı reddedildi.');
    expect(formatHostError(refused)).not.toMatch(/127\.0\.0\.1|2375/);

    const timeout = Object.assign(new Error('Connect Timeout Error https://user:pat@ghcr.io'), {
      code: 'UND_ERR_CONNECT_TIMEOUT',
    });
    expect(classifyHostError(timeout)).toBe('timeout');
    expect(formatHostError(timeout)).toBe('İşlem zaman aşımına uğradı.');
    expect(formatHostError(timeout)).not.toMatch(/pat|ghcr/i);
  });

  it('bilinen Türkçe host cümlesini korur, yabancı istisnayı yutmaz', () => {
    expect(formatHostError(new Error("'run_powershell' iptal edildi."))).toMatch(/iptal/i);
    expect(
      formatHostError(new Error("'C:\\\\Windows\\\\SAM' izin verilen klasörlerin dışında.")),
    ).toMatch(/izin verilen/i);
    expect(formatHostError(new Error("'hedef.txt' zaten var. Üzerine yazılmadı."))).toMatch(
      /zaten var/i,
    );
    expect(formatHostError(new Error('spawn weird ENOBUFS at C:\\secret\\token.txt'))).toBe(
      'İşlem başarısız.',
    );
    expect(formatHostError(new Error('spawn weird ENOBUFS at C:\\secret\\token.txt'))).not.toMatch(
      /secret|token/i,
    );
  });

  it('EPIPE / TLS / yol yok / boş / IPv6 sızmaz', () => {
    const pipe = Object.assign(new Error('write EPIPE'), { code: 'EPIPE' });
    expect(classifyHostError(pipe)).toBe('connection_refused');
    expect(formatHostError(pipe)).toBe('Bağlantı reddedildi.');

    const tls = Object.assign(new Error('certificate has expired for https://user:pat@evil.test'), {
      code: 'UND_ERR_TLS',
    });
    expect(classifyHostError(tls)).toBe('tls');
    expect(formatHostError(tls)).toBe('TLS/sertifika hatası.');
    expect(formatHostError(tls)).not.toMatch(/pat|evil/i);

    const missing = new Error('The system cannot find the path specified');
    expect(classifyHostError(missing)).toBe('not_found');
    expect(formatHostError(missing)).toBe('Program veya yol bulunamadı.');

    expect(formatHostError('')).toBe('İşlem başarısız.');
    expect(formatHostError({ code: 'ENOENT' })).toBe('Program veya yol bulunamadı.');

    const v6 = Object.assign(new Error('connect ECONNREFUSED ::1:2375'), { code: 'ECONNREFUSED' });
    expect(formatHostError(v6)).toBe('Bağlantı reddedildi.');
    expect(formatHostError(v6)).not.toMatch(/::1|2375/);
    expect(formatHostError(new Error('Panoya yazılacak metin boş olamaz.'))).toMatch(/boş olamaz/i);
    expect(formatHostError(new Error('Ses seviyesi 0 ile 100 arasında olmalı.'))).toMatch(/olmalı/i);
  });
});
