/** Odysseus LAN adayları + Home Assistant dış adres süzgeci. */

import { describe, expect, it } from 'vitest';

import { classifyLanAddress, rankLanCandidates } from '../electron/host-tools/lan';

describe('Odysseus lan_ip_candidates', () => {
  it('çıkış IP önce, 127 ve APIPA düşer', () => {
    const ranked = rankLanCandidates({
      egressIp: '192.168.1.40',
      addresses: ['127.0.0.1', '169.254.12.4', '10.0.0.8', '192.168.1.40'],
    });
    expect(ranked.preferred).toBe('192.168.1.40');
    expect(ranked.candidates[0]).toBe('192.168.1.40');
    expect(ranked.candidates).toContain('10.0.0.8');
    expect(ranked.candidates).not.toContain('127.0.0.1');
    expect(ranked.candidates).not.toContain('169.254.12.4');
  });

  it('çıkış loopback ise RFC1918 yedeklenir', () => {
    const ranked = rankLanCandidates({
      egressIp: '127.0.0.1',
      addresses: ['10.8.0.2', '8.8.8.8'],
    });
    expect(ranked.preferred).toBe('10.8.0.2');
    expect(ranked.candidates[0]).toBe('10.8.0.2');
  });
});

describe('Home Assistant dış adres', () => {
  it('loopback / link-local / multicast geçersiz sayılır', () => {
    expect(classifyLanAddress('127.0.0.1')).toBe('loopback');
    expect(classifyLanAddress('169.254.1.1')).toBe('link_local');
    expect(classifyLanAddress('224.0.0.251')).toBe('invalid');
    expect(classifyLanAddress('0.0.0.0')).toBe('invalid');
    expect(classifyLanAddress('10.0.0.1')).toBe('private');
    expect(classifyLanAddress('100.64.1.2')).toBe('cgnat');
    expect(classifyLanAddress('8.8.8.8')).toBe('public');
  });
});
