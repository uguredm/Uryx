/**
 * Host LAN IPv4 sıralaması.
 *
 * Odysseus `lan_ip_candidates`: UDP çıkış IP'si önce, 127 düşer.
 * Home Assistant `_ip_address_is_external`: link-local / multicast / loopback dış.
 */

export type LanAddressKind = 'loopback' | 'link_local' | 'cgnat' | 'private' | 'public' | 'invalid';

const USABLE = new Set<LanAddressKind>(['private', 'cgnat', 'public']);

function parseIpv4(raw: string): [number, number, number, number] | null {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(String(raw ?? '').trim());
  if (!match) return null;
  const parts = [Number(match[1]), Number(match[2]), Number(match[3]), Number(match[4])] as [
    number,
    number,
    number,
    number,
  ];
  if (parts.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) return null;
  return parts;
}

/** RFC1918 / CGNAT / APIPA / loopback ayrımı. */
export function classifyLanAddress(ip: string): LanAddressKind {
  const parts = parseIpv4(ip);
  if (!parts) return 'invalid';
  const [a, b] = parts;
  if (a === 0 || (a >= 224 && a <= 239) || a === 255) return 'invalid';
  if (a === 127) return 'loopback';
  if (a === 169 && b === 254) return 'link_local';
  if (a === 10) return 'private';
  if (a === 192 && b === 168) return 'private';
  if (a === 172 && b >= 16 && b <= 31) return 'private';
  if (a === 100 && b >= 64 && b <= 127) return 'cgnat';
  return 'public';
}

function kindRank(kind: LanAddressKind): number {
  if (kind === 'private') return 0;
  if (kind === 'cgnat') return 1;
  if (kind === 'public') return 2;
  return 9;
}

/**
 * Çıkış IP'si (UDP 8.8.8.8) başta; loopback / APIPA / multicast yok.
 */
export function rankLanCandidates(input: {
  egressIp?: string | null;
  addresses: string[];
}): { preferred: string | null; candidates: string[] } {
  const seen = new Set<string>();
  const usable: string[] = [];

  const add = (raw: string | null | undefined) => {
    const ip = String(raw ?? '').trim();
    if (!ip || seen.has(ip)) return;
    if (!USABLE.has(classifyLanAddress(ip))) return;
    seen.add(ip);
    usable.push(ip);
  };

  add(input.egressIp);
  const rest = [...input.addresses].sort(
    (left, right) => kindRank(classifyLanAddress(left)) - kindRank(classifyLanAddress(right)),
  );
  for (const ip of rest) add(ip);

  return { preferred: usable[0] ?? null, candidates: usable.slice(0, 8) };
}
