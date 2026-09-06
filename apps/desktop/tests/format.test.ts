/** Biçimlendirme yardımcıları testleri. */

import { describe, expect, it } from 'vitest';

import {
  documentStatusLabel,
  formatBytes,
  formatDuration,
  memoryCategoryLabel,
  riskLabel,
  serviceStateLabel,
  truncate,
} from '@/lib/format';

describe('formatBytes', () => {
  it('sıfır ve geçersiz değerler', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(-5)).toBe('0 B');
    expect(formatBytes(Number.NaN)).toBe('0 B');
  });

  it('bayt birimleri', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048, 'tr')).toBe('2,0 KB');
    expect(formatBytes(5 * 1024 * 1024, 'tr')).toBe('5,0 MB');
  });
});

describe('formatDuration', () => {
  it('milisaniye', () => {
    expect(formatDuration(250)).toBe('250 ms');
  });

  it('saniye', () => {
    expect(formatDuration(2500, 'tr')).toBe('2,5 sn');
  });

  it('dakika', () => {
    expect(formatDuration(125_000, 'tr')).toBe('2 dk 5 sn');
  });

  it('geçersiz değer', () => {
    expect(formatDuration(-1)).toBe('—');
  });
});

describe('Türkçe etiketler', () => {
  it('servis durumları', () => {
    expect(serviceStateLabel('up', 'tr')).toBe('Çalışıyor');
    expect(serviceStateLabel('down', 'tr')).toBe('Kapalı');
    expect(serviceStateLabel('bilinmeyen', 'tr')).toBe('bilinmeyen');
  });

  it('hafıza kategorileri', () => {
    expect(memoryCategoryLabel('preference', 'tr')).toBe('Tercih');
    expect(memoryCategoryLabel('system_info', 'tr')).toBe('Sistem bilgisi');
  });

  it('belge durumları', () => {
    expect(documentStatusLabel('indexed', 'tr')).toBe('İndekslendi');
    expect(documentStatusLabel('failed', 'tr')).toBe('Başarısız');
  });

  it('risk seviyeleri', () => {
    expect(riskLabel('high', 'tr')).toBe('Yüksek risk');
    expect(riskLabel('low', 'tr')).toBe('Düşük risk');
    expect(riskLabel('medium', 'en')).toBe('Medium risk');
  });

  it('İngilizce servis / hafıza / belge etiketleri', () => {
    expect(serviceStateLabel('up')).toBe('Running');
    expect(memoryCategoryLabel('preference')).toBe('Preference');
    expect(documentStatusLabel('indexed')).toBe('Indexed');
  });
});

describe('truncate', () => {
  it('kısa metni değiştirmez', () => {
    expect(truncate('kısa', 10)).toBe('kısa');
  });

  it('uzun metni keser', () => {
    expect(truncate('a'.repeat(50), 10)).toBe(`${'a'.repeat(10)}…`);
  });
});
