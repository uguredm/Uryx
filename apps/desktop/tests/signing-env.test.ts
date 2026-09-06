/** Authenticode ortamı — self-signed yok, pfx git’e yok. */

import { describe, expect, it } from 'vitest';

import { resolveSigningMode } from '../electron/signing-env';

describe('resolveSigningMode', () => {
  it('imza değişkeni yoksa none döner — imzalı sayılmaz', () => {
    expect(resolveSigningMode({})).toBe('none');
  });

  it('WIN_CSC_LINK doluysa pfx', () => {
    expect(resolveSigningMode({ WIN_CSC_LINK: 'C:\\certs\\ov.pfx' })).toBe('pfx');
  });

  it('CSC_LINK doluysa pfx', () => {
    expect(resolveSigningMode({ CSC_LINK: '/secret/ov.pfx' })).toBe('pfx');
  });

  it('Azure Trusted Signing tam set ise azure', () => {
    expect(
      resolveSigningMode({
        AZURE_TENANT_ID: 'tenant',
        AZURE_CLIENT_ID: 'client',
        AZURE_CLIENT_SECRET: 'secret',
        AZURE_CODE_SIGNING_ACCOUNT_NAME: 'uryx',
        AZURE_CERT_PROFILE_NAME: 'ov',
      }),
    ).toBe('azure');
  });

  it('Azure eksik set ise none', () => {
    expect(
      resolveSigningMode({
        AZURE_TENANT_ID: 'tenant',
        AZURE_CLIENT_ID: 'client',
      }),
    ).toBe('none');
  });
});
