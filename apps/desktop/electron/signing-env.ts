/** Authenticode ortamı — self-signed yok; .pfx git’e yok. */

export type SigningMode = 'none' | 'pfx' | 'azure';

function present(value: string | undefined): boolean {
  return Boolean(value && value.trim());
}

/** Build ortamından imza kaynağı. `none` = imzasız; “imzalı” demeyin. */
export function resolveSigningMode(
  env: Record<string, string | undefined>,
): SigningMode {
  const azure =
    present(env.AZURE_TENANT_ID) &&
    present(env.AZURE_CLIENT_ID) &&
    present(env.AZURE_CLIENT_SECRET) &&
    present(env.AZURE_CODE_SIGNING_ACCOUNT_NAME ?? env.AZURE_TRUSTED_SIGNING_ACCOUNT) &&
    present(env.AZURE_CERT_PROFILE_NAME ?? env.AZURE_CERTIFICATE_PROFILE_NAME);
  if (azure) return 'azure';
  if (present(env.WIN_CSC_LINK) || present(env.CSC_LINK)) return 'pfx';
  return 'none';
}
