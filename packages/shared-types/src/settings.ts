/** Masaüstü uygulamasının yerel ayarları (electron-store). */

/** D23: HUD tek koyu. `light`/`system` yalnız eski store JSON için; sanitize koyuya kilitler. */
export type ThemeMode = 'dark' | 'light' | 'system';
/** HUD vurgu paleti — varsayılan yeşil (mevcut Uryx). */
export type AccentTheme = 'green' | 'blue';
export const ACCENT_THEMES: readonly AccentTheme[] = ['green', 'blue'];
/** Arayüz dili — D25 taze kurulum İngilizce; kayıtlı `tr` durur. */
export type UiLanguage = 'tr' | 'en';
export const UI_LANGUAGES = ['tr', 'en'] as const;

/** Yerel llama.cpp GGUF profili — Ayarlar kartı. */
export type LlmPreset = 'fast' | 'balanced' | 'quality' | 'agent';
export const LLM_PRESET_IDS = ['fast', 'balanced', 'quality', 'agent'] as const;

export interface LlmPresetSpec {
  id: LlmPreset;
  label: string;
  description: string;
  modelName: string;
  ggufFile: string;
  hfRepo: string;
  contextLength: number;
}

export const LLM_PRESETS: Record<LlmPreset, LlmPresetSpec> = {
  quality: {
    id: 'quality',
    label: '8B kalite',
    description: 'Qwen3-8B Q4_K_M — RTX 5070 varsayılanı, araç ve Türkçe (~5 GB).',
    modelName: 'qwen3-8b',
    ggufFile: 'Qwen3-8B-Q4_K_M.gguf',
    hfRepo: 'unsloth/Qwen3-8B-GGUF',
    contextLength: 8192,
  },
  balanced: {
    id: 'balanced',
    label: '4B dengeli',
    description: 'Qwen3-4B-Instruct-2507 Q4_K_M — düşünmesiz 4B, daha az VRAM (~2.5 GB).',
    modelName: 'qwen3-4b-instruct',
    ggufFile: 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
    hfRepo: 'unsloth/Qwen3-4B-Instruct-2507-GGUF',
    contextLength: 8192,
  },
  fast: {
    id: 'fast',
    label: '1.7B hızlı',
    description: 'Qwen3-1.7B Q4_K_M — zayıf GPU / hızlı deneme (~1.1 GB).',
    modelName: 'qwen3-1.7b',
    ggufFile: 'Qwen3-1.7B-Q4_K_M.gguf',
    hfRepo: 'unsloth/Qwen3-1.7B-GGUF',
    contextLength: 8192,
  },
  agent: {
    id: 'agent',
    label: '9B deneysel',
    description:
      'Qwen3.5-9B Q4_K_M — deneysel; şablon riski. Vision mmproj indirme.',
    modelName: 'qwen3.5-9b',
    ggufFile: 'Qwen3.5-9B-Q4_K_M.gguf',
    hfRepo: 'unsloth/Qwen3.5-9B-GGUF',
    contextLength: 8192,
  },
};

export function resolveLlmPreset(
  modelName: string,
  preset?: string | null,
): LlmPreset {
  const name = modelName.toLowerCase();
  if (
    name === LLM_PRESETS.quality.modelName ||
    name.includes('qwen3-8') ||
    (name.includes('8b') && !name.includes('1.7'))
  ) {
    return 'quality';
  }
  if (
    name === LLM_PRESETS.agent.modelName ||
    name.includes('qwen3.5') ||
    name.includes('3.5-9')
  ) {
    return 'agent';
  }
  if (name === LLM_PRESETS.balanced.modelName || name.includes('qwen3-4')) return 'balanced';
  if (name === LLM_PRESETS.fast.modelName || name.includes('1.7b')) return 'fast';
  if ((LLM_PRESET_IDS as readonly string[]).includes(String(preset ?? ''))) {
    return preset as LlmPreset;
  }
  return 'fast';
}

/** Windows SAPI robotik ses — yalnızca geriye dönük seçenek. */
export const WINDOWS_LEGACY_VOICE = 'windows:Microsoft Tolga - Turkish (Turkey)';
/** Ayarlarda hâlâ görünen eski sabit; Tolga'ya işaret eder. */
export const WINDOWS_TURKISH_VOICE = WINDOWS_LEGACY_VOICE;
/** Edge Neural (internet) — Türkçe varsayılan. */
export const EDGE_NEURAL_VOICE = 'tr-TR-AhmetNeural';
/** Edge Neural — İngilizce varsayılan (D25 taze kurulum). */
export const EDGE_EN_NEURAL_VOICE = 'en-US-GuyNeural';

const LANGUAGE_TTS_DEFAULTS: Record<UiLanguage, string> = {
  tr: EDGE_NEURAL_VOICE,
  en: EDGE_EN_NEURAL_VOICE,
};

const LANGUAGE_FOLLOW_TTS_VOICES = new Set<string>([
  EDGE_NEURAL_VOICE,
  EDGE_EN_NEURAL_VOICE,
  'en-US-JennyNeural',
  'tr_TR-dfki-medium',
  'en_US-lessac-medium',
]);

export function defaultTtsVoiceForLanguage(language: UiLanguage): string {
  return LANGUAGE_TTS_DEFAULTS[language] ?? EDGE_EN_NEURAL_VOICE;
}

/** Dil varsayılanı veya boş ses → dile uygun motor. Emel/Tolga gibi seçim durur. */
export function ttsVoiceForLanguage(language: UiLanguage, current: string): string {
  const voice = current.trim();
  if (!voice || LANGUAGE_FOLLOW_TTS_VOICES.has(voice)) {
    return defaultTtsVoiceForLanguage(language);
  }
  return voice.slice(0, 100);
}

export interface McpServerConfig {
  id: string;
  command: string;
  args: string[];
  allowedTools: string[];
  /** Yalnızca allowlist'li anahtarlar (electron-store; repoya yazılmaz). */
  env?: Record<string, string>;
}

/** Ayar JSON / electron-store → MCP çocuğu. Süreç ortamından kopyalanmaz. */
export const MCP_SERVER_ENV_KEYS = [
  'CONTEXT7_API_KEY',
  'GITHUB_PERSONAL_ACCESS_TOKEN',
  'DISABLE_THOUGHT_LOGGING',
  'BRAVE_API_KEY',
  'HF_TOKEN',
  'DDG_REGION',
  'DDG_SAFE_SEARCH',
  'LIBRETRANSLATE_API_URL',
  'LIBRETRANSLATE_API_KEY',
  'GEOCODE_USER_AGENT',
] as const;

export type McpServerEnvKey = (typeof MCP_SERVER_ENV_KEYS)[number];

export type McpRecipeKind = 'recommended' | 'opt-in';
export type McpRecipeGroupId = 'recommended' | 'code' | 'search' | 'knowledge';

export interface McpRecipeEnvField {
  key: McpServerEnvKey;
  label: string;
  hint: string;
}

export interface McpRecipeMeta {
  id: string;
  kind: McpRecipeKind;
  group: McpRecipeGroupId;
  title: string;
  description: string;
  runtime: 'uvx' | 'npx';
  env?: readonly McpRecipeEnvField[];
}

export const MCP_RECIPE_GROUP_LABELS: Record<McpRecipeGroupId, string> = {
  recommended: 'Önerilen',
  code: 'Geliştirici',
  search: 'Arama',
  knowledge: 'Bilgi',
};

/** electron-store kaydında tutulan sunucu tavanı. */
export const MCP_SERVERS_STORE_CAP = 20;
/** Ayar JSON satırında kabul edilen komut tabanları (docker/cmd yok). */
export const MCP_JSON_COMMANDS = [
  'npx',
  'npx.cmd',
  'npx.bat',
  'npm',
  'npm.cmd',
  'npm.bat',
  'pnpm',
  'pnpm.exe',
  'pnpm.cmd',
  'pnpm.bat',
  'pnpx',
  'pnpx.exe',
  'pnpx.cmd',
  'pnpx.bat',
  'yarn',
  'yarn.exe',
  'yarn.cmd',
  'yarn.bat',
  'node',
  'node.exe',
  'node.cmd',
  'node.bat',
  'bun',
  'bun.exe',
  'bun.cmd',
  'bun.bat',
  'bunx',
  'bunx.exe',
  'bunx.cmd',
  'bunx.bat',
  'uvx',
  'uvx.exe',
  'uvx.cmd',
  'uvx.bat',
  'uv',
  'uv.exe',
  'uv.cmd',
  'uv.bat',
  'python',
  'python.exe',
  'python.cmd',
  'python.bat',
  'pythonw',
  'pythonw.exe',
  'python3',
  'python3.exe',
  'py',
  'py.exe',
  'py.cmd',
  'py.bat',
] as const;

/** Yalnızca çıplak komut veya mutlak yol — UNC, göreli, `C:npx` ve `..` yok. */
export function mcpCommandPathAllowed(command: string): boolean {
  const trimmed = command.trim();
  if (!trimmed || /[\0\t\v\f\r\n]/.test(trimmed)) return false;
  if (trimmed.startsWith('\\\\') || trimmed.startsWith('//')) return false;
  if (/(^|[\\/])\.\.([\\/]|$)/.test(trimmed)) return false;
  if (/^[a-zA-Z]:[^\\/]/.test(trimmed)) return false;
  const base = trimmed.replace(/^.*[/\\]/, '');
  if (!base) return false;
  if (base === trimmed) return true;
  if (/^[a-zA-Z]:[\\/]/.test(trimmed)) return true;
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) return true;
  return false;
}

/** İlk paket indirmesi + stdio initialize tavanı. */
export const MCP_SPAWN_TIMEOUT_MS = 40_000;
export const MCP_INIT_TIMEOUT_MS = MCP_SPAWN_TIMEOUT_MS;
/** initialize sonrası tools/list veya tools/call. */
export const MCP_RPC_TIMEOUT_MS = 20_000;
export const MCP_HOST_TIMEOUT_MS = MCP_INIT_TIMEOUT_MS + MCP_RPC_TIMEOUT_MS + 5_000;
export const MCP_FIRST_RUN_HINT =
  'İlk npx/uvx indirmesi ~40 sn sürebilir; zaman aşımı 40 sn.';

export const MCP_OVERLAP_SUMMARY =
  'Yerleşik web_search, weather, wiki_lookup ve fx_rate MCP’siz çalışır. DuckDuckGo / Open-Meteo / Wikipedia kartları aynı işi onaylı mcp_call ile tekrarlar. Frankfurter MCP yok — kur için fx_rate.';

export const MCP_NATIVE_OVERLAP_NOTES = [
  {
    id: 'ddg',
    native: 'web_search',
    copy: 'Günlük arama için yerleşik web_search yeter. DuckDuckGo MCP aynı dizini ikinci kez açar; sayfa çekmez (web_fetch).',
  },
  {
    id: 'weather',
    native: 'weather',
    copy: 'Hava için yerleşik weather (Open-Meteo) yeter. Bu kart ek tahmin/kalite/deniz içindir; mcp_call onay ister.',
  },
  {
    id: 'wikipedia',
    native: 'wiki_lookup',
    copy: 'Madde özeti için yerleşik wiki_lookup yeter. Wikipedia MCP arama/bölüm içindir; mcp_call onay ister.',
  },
  {
    id: 'fx',
    native: 'fx_rate',
    copy: 'Kur için yerleşik fx_rate kullanın. Frankfurter MCP katalogda yok.',
  },
] as const;

export function mcpNativeOverlapNote(id: string): string | undefined {
  return MCP_NATIVE_OVERLAP_NOTES.find((note) => note.id === id)?.copy;
}

/**
 * Uryx ürünü için küçük, bakımlı katalog.
 * filesystem / git / memory MCP yok — host araçları ve yerel hafıza zaten var.
 * mcpEnabled varsayılan kapalı; kullanıcı Ayarlar'dan açar.
 */
export const RECOMMENDED_MCP_SERVERS: McpServerConfig[] = [
  {
    id: 'fetch',
    command: 'uvx',
    args: ['mcp-server-fetch'],
    allowedTools: ['fetch'],
  },
  {
    id: 'time',
    command: 'uvx',
    args: ['mcp-server-time', '--local-timezone=Europe/Istanbul'],
    allowedTools: ['get_current_time', 'convert_time'],
  },
  {
    id: 'docs',
    command: 'npx',
    args: ['-y', '@upstash/context7-mcp'],
    allowedTools: ['resolve-library-id', 'query-docs', 'get-library-docs'],
  },
  {
    id: 'think',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-sequential-thinking'],
    allowedTools: ['sequential_thinking'],
  },
];

/**
 * Playwright MCP tarif kartı — native 26 araç dökümü değil.
 * Yalnızca gezinme + a11y snapshot. Tıklama/yazma/evaluate yok (serbest fare yok).
 * Etkileşim: Uryx `browser_*` veya JSON'a ekleyip `mcp_call` (HIGH + onay).
 */
export const PLAYWRIGHT_MCP_RECIPE: McpServerConfig = {
  id: 'playwright',
  command: 'npx',
  args: ['-y', '@playwright/mcp', '--isolated'],
  allowedTools: [
    'browser_navigate',
    'browser_navigate_back',
    'browser_snapshot',
    'browser_take_screenshot',
    'browser_tabs',
    'browser_wait_for',
    'browser_close',
  ],
};

function cloneMcpServer(server: McpServerConfig): McpServerConfig {
  return {
    ...server,
    args: [...server.args],
    allowedTools: [...server.allowedTools],
    ...(server.env ? { env: { ...server.env } } : {}),
  };
}

export function cloneRecommendedMcpServers(): McpServerConfig[] {
  return RECOMMENDED_MCP_SERVERS.map(cloneMcpServer);
}

export function clonePlaywrightMcpRecipe(): McpServerConfig {
  return cloneMcpServer(PLAYWRIGHT_MCP_RECIPE);
}

/**
 * GitHub MCP tarif kartı — docker spawn yok (`docker` komut allowlist'te yok).
 * npx + `@modelcontextprotocol/server-github`; PAT: `GITHUB_PERSONAL_ACCESS_TOKEN`.
 * Tarif salt okuma; yazma araçları JSON'a eklenirse yine `mcp_call` HIGH+onay.
 */
export const GITHUB_MCP_RECIPE: McpServerConfig = {
  id: 'github',
  command: 'npx',
  args: ['-y', '@modelcontextprotocol/server-github'],
  allowedTools: [
    'search_repositories',
    'search_code',
    'search_issues',
    'search_users',
    'get_file_contents',
    'list_commits',
    'list_issues',
    'get_issue',
    'list_pull_requests',
    'get_pull_request',
    'get_pull_request_files',
    'get_pull_request_status',
    'get_pull_request_comments',
    'get_pull_request_reviews',
  ],
};

export function cloneGithubMcpRecipe(): McpServerConfig {
  return cloneMcpServer(GITHUB_MCP_RECIPE);
}

/**
 * Brave Search tarif kartı — resmi `@brave/brave-search-mcp-server`, stdio varsayılan.
 * Native `web_search` / görsel / video durur; bu kart ücretli Brave API içindir.
 * HTTP transport yok (`--transport http` eklenmez).
 */
export const BRAVE_MCP_RECIPE: McpServerConfig = {
  id: 'brave',
  command: 'npx',
  args: ['-y', '@brave/brave-search-mcp-server'],
  allowedTools: [
    'brave_web_search',
    'brave_local_search',
    'brave_news_search',
    'brave_place_search',
  ],
};

export function cloneBraveMcpRecipe(): McpServerConfig {
  return cloneMcpServer(BRAVE_MCP_RECIPE);
}

/**
 * Hugging Face Hub tarif kartı — resmi `npx @llmindset/hf-mcp-server` (stdio paketi).
 * Salt arama/belge; hf_jobs / hf_fs / Gradio çalıştırma yok. Docker spawn yok.
 */
export const HUGGINGFACE_MCP_RECIPE: McpServerConfig = {
  id: 'huggingface',
  command: 'npx',
  args: ['-y', '@llmindset/hf-mcp-server'],
  allowedTools: [
    'model_search',
    'dataset_search',
    'space_search',
    'paper_search',
    'hub_repo_search',
    'hub_repo_details',
    'hf_doc_search',
    'hf_doc_fetch',
    'hf_whoami',
  ],
};

export function cloneHuggingfaceMcpRecipe(): McpServerConfig {
  return cloneMcpServer(HUGGINGFACE_MCP_RECIPE);
}

/**
 * Open-Meteo hava — IBM `chuk-mcp-open-meteo` (uvx, anahtar yok).
 * `http` argümanı yok: stdio; localhost HTTP dinlemez.
 */
export const WEATHER_MCP_RECIPE: McpServerConfig = {
  id: 'weather',
  command: 'uvx',
  args: ['chuk-mcp-open-meteo'],
  allowedTools: [
    'get_weather_forecast',
    'geocode_location',
    'get_historical_weather',
    'get_air_quality',
    'get_marine_forecast',
    'interpret_weather_code',
    'batch_geocode_locations',
    'batch_get_weather_forecasts',
    'batch_get_air_quality',
    'batch_get_marine_forecasts',
    'batch_get_historical_weather',
    'batch_interpret_weather_codes',
  ],
};

export function cloneWeatherMcpRecipe(): McpServerConfig {
  return cloneMcpServer(WEATHER_MCP_RECIPE);
}

/**
 * Wikipedia — `@cyanheads/wikipedia-mcp-server` (npx, anahtar yok).
 * Salt okuma; docker / HTTP transport yok. Yerel dosya yazmaz.
 */
export const WIKIPEDIA_MCP_RECIPE: McpServerConfig = {
  id: 'wikipedia',
  command: 'npx',
  args: ['-y', '@cyanheads/wikipedia-mcp-server'],
  allowedTools: [
    'wikipedia_search',
    'wikipedia_get_summary',
    'wikipedia_get_article',
    'wikipedia_get_sections',
    'wikipedia_search_nearby',
    'wikipedia_get_languages',
  ],
};

export function cloneWikipediaMcpRecipe(): McpServerConfig {
  return cloneMcpServer(WIKIPEDIA_MCP_RECIPE);
}

/**
 * arXiv — `uvx arxiv-mcp-server`. Yalnızca uzak arama/özet/atıf.
 * İndirme, yerel kağıt listesi, watch ve semantik indeks yok (disk yazmaz).
 */
export const ARXIV_MCP_RECIPE: McpServerConfig = {
  id: 'arxiv',
  command: 'uvx',
  args: ['arxiv-mcp-server'],
  allowedTools: ['search_papers', 'get_abstract', 'citation_graph', 'export_citations'],
};

export function cloneArxivMcpRecipe(): McpServerConfig {
  return cloneMcpServer(ARXIV_MCP_RECIPE);
}

/**
 * Wikidata — `@cyanheads/wikidata-mcp-server` (npx, anahtar yok).
 * Salt okuma bilgi grafiği; SPARQL SELECT. Docker / HTTP yok.
 */
export const WIKIDATA_MCP_RECIPE: McpServerConfig = {
  id: 'wikidata',
  command: 'npx',
  args: ['-y', '@cyanheads/wikidata-mcp-server'],
  allowedTools: [
    'wikidata_search_entities',
    'wikidata_get_entity',
    'wikidata_get_labels',
    'wikidata_get_statements',
    'wikidata_get_sitelinks',
    'wikidata_sparql_query',
    'wikidata_resolve_external_id',
  ],
};

export function cloneWikidataMcpRecipe(): McpServerConfig {
  return cloneMcpServer(WIKIDATA_MCP_RECIPE);
}

/**
 * YouTube altyazı — PyPI `mcp-youtube-transcript` (uvx, git+ yok).
 * Salt okuma; indirme/tıklama yok. Dil aracı `lang=tr` ile Türkçe iz.
 */
export const YOUTUBE_MCP_RECIPE: McpServerConfig = {
  id: 'youtube',
  command: 'uvx',
  args: ['mcp-youtube-transcript'],
  allowedTools: [
    'get_transcript',
    'get_timed_transcript',
    'get_video_info',
    'get_available_languages',
  ],
};

export function cloneYoutubeMcpRecipe(): McpServerConfig {
  return cloneMcpServer(YOUTUBE_MCP_RECIPE);
}

/**
 * Hacker News — `@cyanheads/hn-mcp-server` (npx, anahtar yok).
 * Salt okuma akış/yorum/arama. Docker / HTTP yok.
 */
export const HACKERNEWS_MCP_RECIPE: McpServerConfig = {
  id: 'hn',
  command: 'npx',
  args: ['-y', '@cyanheads/hn-mcp-server'],
  allowedTools: ['hn_get_stories', 'hn_get_thread', 'hn_get_user', 'hn_search_content'],
};

export function cloneHackernewsMcpRecipe(): McpServerConfig {
  return cloneMcpServer(HACKERNEWS_MCP_RECIPE);
}

/**
 * DuckDuckGo — `uvx duckduckgo-mcp-server`. Anahtar yok.
 * Yalnız `search` (fetch_content yok — Uryx `web_fetch` durur).
 * Bölge varsayılanı tr-tr; HTTP transport yok.
 */
export const DUCKDUCKGO_MCP_RECIPE: McpServerConfig = {
  id: 'ddg',
  command: 'uvx',
  args: ['duckduckgo-mcp-server'],
  allowedTools: ['search'],
  env: { DDG_REGION: 'tr-tr', DDG_SAFE_SEARCH: 'MODERATE' },
};

export function cloneDuckduckgoMcpRecipe(): McpServerConfig {
  return cloneMcpServer(DUCKDUCKGO_MCP_RECIPE);
}

/**
 * Open Library — `@cyanheads/openlibrary-mcp-server` (npx, anahtar yok).
 * Kitap/ISBN/yazar; indirme yok. Docker / HTTP yok.
 */
export const OPENLIBRARY_MCP_RECIPE: McpServerConfig = {
  id: 'openlibrary',
  command: 'npx',
  args: ['-y', '@cyanheads/openlibrary-mcp-server'],
  allowedTools: [
    'openlibrary_search_books',
    'openlibrary_get_work',
    'openlibrary_get_editions',
    'openlibrary_get_edition',
    'openlibrary_search_authors',
    'openlibrary_get_author',
  ],
};

export function cloneOpenlibraryMcpRecipe(): McpServerConfig {
  return cloneMcpServer(OPENLIBRARY_MCP_RECIPE);
}

/**
 * LibreTranslate — resmi `@libretranslate/mcp` (npx).
 * Yerel veya kendi URL. Public instance anahtar ister. Docker yok.
 */
export const TRANSLATE_MCP_RECIPE: McpServerConfig = {
  id: 'translate',
  command: 'npx',
  args: ['-y', '@libretranslate/mcp'],
  allowedTools: ['detect', 'translate', 'languages'],
  env: { LIBRETRANSLATE_API_URL: 'https://libretranslate.com' },
};

export function cloneTranslateMcpRecipe(): McpServerConfig {
  return cloneMcpServer(TRANSLATE_MCP_RECIPE);
}

/**
 * RSS — `npx -y rss-mcp`. Yalnız `get_feed` (yazma/yerel dosya yok).
 * Türkçe haber akışları için http(s) URL.
 */
export const RSS_MCP_RECIPE: McpServerConfig = {
  id: 'rss',
  command: 'npx',
  args: ['-y', 'rss-mcp'],
  allowedTools: ['get_feed'],
};

export function cloneRssMcpRecipe(): McpServerConfig {
  return cloneMcpServer(RSS_MCP_RECIPE);
}

/**
 * OSM Nominatim — `npx -y geocode-mcp`. Anahtar yok.
 * Overpass ham sorgu yok. User-Agent Nominatim politikası için.
 */
export const GEOCODE_MCP_RECIPE: McpServerConfig = {
  id: 'geocode',
  command: 'npx',
  args: ['-y', 'geocode-mcp'],
  allowedTools: ['geocode', 'reverse_geocode', 'search_places', 'distance_between'],
  env: { GEOCODE_USER_AGENT: 'Uryx local assistant' },
};

export function cloneGeocodeMcpRecipe(): McpServerConfig {
  return cloneMcpServer(GEOCODE_MCP_RECIPE);
}

/** Önerilen + opt-in tarifler — Ayarlar kartları JSON yazmadan açar. */
export const MCP_RECIPE_CATALOG: readonly McpRecipeMeta[] = [
  {
    id: 'fetch',
    kind: 'recommended',
    group: 'recommended',
    title: 'Fetch',
    description: 'URL’yi markdown olarak okur (resmî MCP Fetch).',
    runtime: 'uvx',
  },
  {
    id: 'time',
    kind: 'recommended',
    group: 'recommended',
    title: 'Saat',
    description: 'IANA saat dilimi; yerel Europe/Istanbul.',
    runtime: 'uvx',
  },
  {
    id: 'docs',
    kind: 'recommended',
    group: 'recommended',
    title: 'Belgeler (Context7)',
    description: 'Kütüphane belgesi. İsteğe bağlı Context7 anahtarı hız limiti açar.',
    runtime: 'npx',
    env: [
      {
        key: 'CONTEXT7_API_KEY',
        label: 'Context7 API anahtarı',
        hint: 'İsteğe bağlı. Yalnızca bu bilgisayarda saklanır; git’e yazılmaz.',
      },
    ],
  },
  {
    id: 'think',
    kind: 'recommended',
    group: 'recommended',
    title: 'Adım adım düşünme',
    description: 'Çok adımlı plan (sequential thinking).',
    runtime: 'npx',
  },
  {
    id: 'playwright',
    kind: 'opt-in',
    group: 'code',
    title: 'Playwright',
    description: 'Gezinme + erişilebilirlik ağacı. Tıklama/yazma yok.',
    runtime: 'npx',
  },
  {
    id: 'github',
    kind: 'opt-in',
    group: 'code',
    title: 'GitHub',
    description: 'Salt okuma (arama, dosya, issue/PR). Docker yok; npx resmi paket.',
    runtime: 'npx',
    env: [
      {
        key: 'GITHUB_PERSONAL_ACCESS_TOKEN',
        label: 'GitHub kişisel erişim jetonu',
        hint: 'İsteğe bağlı PAT. electron-store; git’e koyulmaz.',
      },
    ],
  },
  {
    id: 'brave',
    kind: 'opt-in',
    group: 'search',
    title: 'Brave Search',
    description: 'Brave API ile web/haber/yerel arama. Yerleşik web_search durur.',
    runtime: 'npx',
    env: [
      {
        key: 'BRAVE_API_KEY',
        label: 'Brave Search API anahtarı',
        hint: 'search.brave.com/search/api — store’da kalır, git’e yazılmaz.',
      },
    ],
  },
  {
    id: 'huggingface',
    kind: 'opt-in',
    group: 'code',
    title: 'Hugging Face',
    description: 'Model/veri/makale/belge arama. İş çalıştırma ve Hub dosya sistemi yok.',
    runtime: 'npx',
    env: [
      {
        key: 'HF_TOKEN',
        label: 'Hugging Face jetonu',
        hint: 'İsteğe bağlı. Rate limit için. Store’da; git’e yazılmaz.',
      },
    ],
  },
  {
    id: 'weather',
    kind: 'opt-in',
    group: 'knowledge',
    title: 'Hava (Open-Meteo)',
    description: 'Yerleşik weather yeter; bu kart ek Open-Meteo (tahmin/kalite). mcp_call onay.',
    runtime: 'uvx',
  },
  {
    id: 'wikipedia',
    kind: 'opt-in',
    group: 'knowledge',
    title: 'Wikipedia',
    description: 'Yerleşik wiki_lookup yeter; bu kart madde ara/bölüm. mcp_call onay.',
    runtime: 'npx',
  },
  {
    id: 'arxiv',
    kind: 'opt-in',
    group: 'knowledge',
    title: 'arXiv',
    description: 'Makale ara, özet, atıf. İndirme ve yerel klasör yok.',
    runtime: 'uvx',
  },
  {
    id: 'wikidata',
    kind: 'opt-in',
    group: 'knowledge',
    title: 'Wikidata',
    description: 'Varlık, ifade, SPARQL. Anahtar yok. Yazma yok.',
    runtime: 'npx',
  },
  {
    id: 'youtube',
    kind: 'opt-in',
    group: 'knowledge',
    title: 'YouTube altyazı',
    description: 'Video metni / zaman damgalı iz. İndirme yok. lang=tr Türkçe.',
    runtime: 'uvx',
  },
  {
    id: 'hn',
    kind: 'opt-in',
    group: 'search',
    title: 'Hacker News',
    description: 'Akış, yorum, arama. Anahtar yok. Yazma yok.',
    runtime: 'npx',
  },
  {
    id: 'ddg',
    kind: 'opt-in',
    group: 'search',
    title: 'DuckDuckGo',
    description: 'Yerleşik web_search yeter; bu kart DDG arama (sayfa yok). mcp_call onay.',
    runtime: 'uvx',
    env: [
      {
        key: 'DDG_REGION',
        label: 'Bölge kodu',
        hint: 'Örn. tr-tr. Store’da kalır; sır değil ama git’e yazılmaz.',
      },
      {
        key: 'DDG_SAFE_SEARCH',
        label: 'SafeSearch',
        hint: 'STRICT, MODERATE veya OFF.',
      },
    ],
  },
  {
    id: 'openlibrary',
    kind: 'opt-in',
    group: 'knowledge',
    title: 'Open Library',
    description: 'Kitap, ISBN, yazar. Anahtar yok. Dosya indirme yok.',
    runtime: 'npx',
  },
  {
    id: 'translate',
    kind: 'opt-in',
    group: 'knowledge',
    title: 'Çeviri (LibreTranslate)',
    description: 'Metin çevir / dil tanı. Yerel URL veya public anahtar.',
    runtime: 'npx',
    env: [
      {
        key: 'LIBRETRANSLATE_API_URL',
        label: 'LibreTranslate adresi',
        hint: 'Varsayılan public API. Kendi sunucunuzun http(s) adresi.',
      },
      {
        key: 'LIBRETRANSLATE_API_KEY',
        label: 'LibreTranslate anahtarı',
        hint: 'Public instance için gerekir. Store’da; git’e yazılmaz.',
      },
    ],
  },
  {
    id: 'rss',
    kind: 'opt-in',
    group: 'search',
    title: 'RSS',
    description: 'Akış oku (get_feed). Yerel kayıt/yazma yok.',
    runtime: 'npx',
  },
  {
    id: 'geocode',
    kind: 'opt-in',
    group: 'knowledge',
    title: 'Yer (OSM)',
    description: 'Adres/koordinat (Nominatim). Anahtar yok. Ham Overpass yok.',
    runtime: 'npx',
    env: [
      {
        key: 'GEOCODE_USER_AGENT',
        label: 'Nominatim User-Agent',
        hint: 'OSM politikası. Varsayılan yeter; e-posta ekleyebilirsiniz. Git’e yazılmaz.',
      },
    ],
  },
];

export function cloneMcpRecipeById(id: string): McpServerConfig | undefined {
  const recommended = RECOMMENDED_MCP_SERVERS.find((server) => server.id === id);
  if (recommended) return cloneMcpServer(recommended);
  if (id === PLAYWRIGHT_MCP_RECIPE.id) return clonePlaywrightMcpRecipe();
  if (id === GITHUB_MCP_RECIPE.id) return cloneGithubMcpRecipe();
  if (id === BRAVE_MCP_RECIPE.id) return cloneBraveMcpRecipe();
  if (id === HUGGINGFACE_MCP_RECIPE.id) return cloneHuggingfaceMcpRecipe();
  if (id === WEATHER_MCP_RECIPE.id) return cloneWeatherMcpRecipe();
  if (id === WIKIPEDIA_MCP_RECIPE.id) return cloneWikipediaMcpRecipe();
  if (id === ARXIV_MCP_RECIPE.id) return cloneArxivMcpRecipe();
  if (id === WIKIDATA_MCP_RECIPE.id) return cloneWikidataMcpRecipe();
  if (id === YOUTUBE_MCP_RECIPE.id) return cloneYoutubeMcpRecipe();
  if (id === HACKERNEWS_MCP_RECIPE.id) return cloneHackernewsMcpRecipe();
  if (id === DUCKDUCKGO_MCP_RECIPE.id) return cloneDuckduckgoMcpRecipe();
  if (id === OPENLIBRARY_MCP_RECIPE.id) return cloneOpenlibraryMcpRecipe();
  if (id === TRANSLATE_MCP_RECIPE.id) return cloneTranslateMcpRecipe();
  if (id === RSS_MCP_RECIPE.id) return cloneRssMcpRecipe();
  if (id === GEOCODE_MCP_RECIPE.id) return cloneGeocodeMcpRecipe();
  return undefined;
}

export function hasMcpServer(servers: McpServerConfig[], id: string): boolean {
  return servers.some((server) => server.id === id);
}

export function setMcpRecipeEnabled(
  servers: McpServerConfig[],
  recipe: McpServerConfig,
  enabled: boolean,
): McpServerConfig[] {
  if (enabled) return mergeMcpRecipe(servers, recipe);
  return servers.filter((server) => server.id !== recipe.id).map(cloneMcpServer);
}

export function setMcpServerEnvValue(
  servers: McpServerConfig[],
  id: string,
  key: string,
  value: string,
): McpServerConfig[] {
  const normalized = key.trim().toUpperCase();
  return servers.map((server) => {
    if (server.id !== id) return cloneMcpServer(server);
    const env = { ...(server.env ?? {}) };
    const next = value.trim();
    if (next) env[normalized] = next;
    else delete env[normalized];
    const clone = cloneMcpServer(server);
    if (Object.keys(env).length > 0) clone.env = env;
    else delete clone.env;
    return clone;
  });
}

/** Önerilen katalogu yazar; playwright/github gibi ekstra tarifleri korur. */
export function applyRecommendedMcpServers(current: McpServerConfig[]): McpServerConfig[] {
  const recommendedIds = new Set(RECOMMENDED_MCP_SERVERS.map((server) => server.id));
  const extras = current.filter((server) => !recommendedIds.has(server.id)).map(cloneMcpServer);
  return [...cloneRecommendedMcpServers(), ...extras];
}

/** Yalnızca önerilen dördü bırakır; opt-in tarifleri ve özel JSON satırlarını siler. */
export function keepRecommendedMcpServers(current: McpServerConfig[]): McpServerConfig[] {
  const recommendedIds = new Set(RECOMMENDED_MCP_SERVERS.map((server) => server.id));
  const kept = current.filter((server) => recommendedIds.has(server.id)).map(cloneMcpServer);
  return kept.length > 0 ? kept : cloneRecommendedMcpServers();
}

export function clearAllMcpServers(): McpServerConfig[] {
  return [];
}

export function describeMcpServersJson(
  raw: string,
  language: UiLanguage = 'en',
): { ok: true; count: number; hint?: string } | { ok: false; error: string } {
  const tr = language === 'tr';
  const cmdWord = tr ? 'komut' : 'command';
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return { ok: false, error: tr ? 'MCP listesi dizi olmalı.' : 'MCP list must be an array.' };
    }
    const seen = new Set<string>();
    const allowed = new Set<string>(MCP_JSON_COMMANDS);
    for (const [index, item] of parsed.entries()) {
      if (!item || typeof item !== 'object' || Array.isArray(item)) {
        return {
          ok: false,
          error: tr
            ? `MCP satırı ${index + 1} bir nesne olmalı.`
            : `MCP row ${index + 1} must be an object.`,
        };
      }
      const row = item as Record<string, unknown>;
      const id = String(row.id ?? '')
        .trim()
        .toLowerCase();
      if (!/^[a-z0-9][a-z0-9_-]{0,39}$/.test(id)) {
        return {
          ok: false,
          error: tr
            ? `MCP satırı ${index + 1}: kimlik geçersiz.`
            : `MCP row ${index + 1}: id is invalid.`,
        };
      }
      if (seen.has(id)) {
        return {
          ok: false,
          error: tr ? `'${id}' kimliği tekrar ediyor.` : `'${id}' id is duplicated.`,
        };
      }
      seen.add(id);
      const command = String(row.command ?? '').trim();
      const base = command.replace(/^.*[/\\]/, '').toLowerCase();
      if (!mcpCommandPathAllowed(command) || !allowed.has(base)) {
        return {
          ok: false,
          error: tr
            ? `'${base || cmdWord}' MCP komut allowlist'inde değil.`
            : `'${base || cmdWord}' is not on the MCP command allowlist.`,
        };
      }
      if (row.args !== undefined && !Array.isArray(row.args)) {
        return {
          ok: false,
          error: tr
            ? `'${id}' args alanı dizi olmalı.`
            : `'${id}' args must be an array.`,
        };
      }
      if (row.allowedTools !== undefined && !Array.isArray(row.allowedTools)) {
        return {
          ok: false,
          error: tr
            ? `'${id}' allowedTools alanı dizi olmalı.`
            : `'${id}' allowedTools must be an array.`,
        };
      }
    }
    const count = parsed.length;
    if (count >= MCP_SERVERS_STORE_CAP) {
      return {
        ok: true,
        count,
        hint: tr
          ? `En fazla ${MCP_SERVERS_STORE_CAP} sunucu kaydedilir; fazlası düşer.`
          : `At most ${MCP_SERVERS_STORE_CAP} servers are saved; extras are dropped.`,
      };
    }
    return { ok: true, count };
  } catch {
    return {
      ok: false,
      error: tr ? 'MCP sunucu JSON’u geçersiz.' : 'MCP server JSON is invalid.',
    };
  }
}

export function parseMcpServersJson(raw: string): McpServerConfig[] | null {
  const state = describeMcpServersJson(raw);
  if (!state.ok) return null;
  try {
    return JSON.parse(raw) as McpServerConfig[];
  } catch {
    return null;
  }
}

/** Gelişmiş JSON taslağı kayıttan farklıysa Kaydet açılsın. */
export function mcpSettingsFormDirty(saved: McpServerConfig[], editorJson: string): boolean {
  return editorJson !== JSON.stringify(saved, null, 2);
}

export function filterMcpRecipeCatalog(
  cards: readonly McpRecipeMeta[],
  query: string,
): McpRecipeMeta[] {
  const needle = query.trim().toLocaleLowerCase('tr-TR');
  if (!needle) return [...cards];
  return cards.filter((card) => {
    const haystack = `${card.id} ${card.title} ${card.description} ${card.runtime} ${card.group}`;
    return haystack.toLocaleLowerCase('tr-TR').includes(needle);
  });
}

export function mcpRecipeIdsInGroup(group: McpRecipeGroupId): string[] {
  return MCP_RECIPE_CATALOG.filter((card) => card.group === group).map((card) => card.id);
}

export function mcpRecipeGroupActive(servers: McpServerConfig[], group: McpRecipeGroupId): boolean {
  return mcpRecipeIdsInGroup(group).some((id) => hasMcpServer(servers, id));
}

export function setMcpRecipeGroupEnabled(
  servers: McpServerConfig[],
  group: McpRecipeGroupId,
  enabled: boolean,
): McpServerConfig[] {
  const ids = new Set(mcpRecipeIdsInGroup(group));
  if (!enabled) {
    return servers.filter((server) => !ids.has(server.id)).map(cloneMcpServer);
  }
  let next = servers.map(cloneMcpServer);
  for (const id of ids) {
    const recipe = cloneMcpRecipeById(id);
    if (recipe) next = mergeMcpRecipe(next, recipe);
  }
  return next;
}

export function mergeMcpRecipe(
  servers: McpServerConfig[],
  recipe: McpServerConfig,
): McpServerConfig[] {
  const clone = cloneMcpServer(recipe);
  const existing = servers.find((server) => server.id === clone.id);
  if (existing?.env && !clone.env) clone.env = { ...existing.env };
  return [...servers.filter((server) => server.id !== clone.id).map(cloneMcpServer), clone];
}

export interface AppSettings {
  backendUrl: string;
  vllmUrl: string;
  localToken: string;

  modelName: string;
  llmPreset: LlmPreset;
  contextLength: number;
  gpuMemoryUtilization: number;
  temperature: number;
  maxTokens: number;

  whisperModel: string;
  microphoneDeviceId: string;
  micNoiseThreshold: number;
  adaptiveVadEnabled: boolean;
  vadEnabled: boolean;
  voiceAutoSend: boolean;
  vadSilenceTimeoutMs: number;
  followUpListenMs: number;

  ttsEnabled: boolean;
  ttsVoice: string;
  ttsSpeed: number;
  ttsVolume: number;

  mcpEnabled: boolean;
  mcpServers: McpServerConfig[];

  wakeWordEnabled: boolean;
  wakeWord: string;
  bargeInEnabled: boolean;

  autoMemoryEnabled: boolean;
  ragEnabled: boolean;
  ragTopK: number;

  thinkingMode: boolean;
  conciseMode: boolean;
  toolsEnabled: boolean;

  theme: ThemeMode;
  accentTheme: AccentTheme;
  launchOnStartup: boolean;
  minimizeToTray: boolean;
  closeToTray: boolean;
  globalShortcut: string;
  pushToTalkKey: string;
  requireRiskConfirmation: boolean;
  language: UiLanguage;
}

export const DEFAULT_SETTINGS: AppSettings = {
  backendUrl: 'http://127.0.0.1:8080',
  vllmUrl: 'http://127.0.0.1:8000/v1',
  localToken: '',

  modelName: 'qwen3-8b',
  llmPreset: 'quality',
  contextLength: 8192,
  gpuMemoryUtilization: 0.7,
  temperature: 0.7,
  maxTokens: 1024,

  whisperModel: 'medium',
  microphoneDeviceId: 'default',
  micNoiseThreshold: 0.012,
  adaptiveVadEnabled: true,
  vadEnabled: true,
  voiceAutoSend: true,
  vadSilenceTimeoutMs: 1400,
  followUpListenMs: 30_000,

  ttsEnabled: true,
  ttsVoice: EDGE_EN_NEURAL_VOICE,
  ttsSpeed: 1.0,
  ttsVolume: 1.0,

  mcpEnabled: false,
  mcpServers: [],

  wakeWordEnabled: false,
  wakeWord: 'uryx',
  bargeInEnabled: false,

  autoMemoryEnabled: true,
  ragEnabled: true,
  ragTopK: 5,

  thinkingMode: false,
  conciseMode: false,
  toolsEnabled: true,

  theme: 'dark',
  accentTheme: 'green',
  launchOnStartup: false,
  minimizeToTray: false,
  closeToTray: true,
  globalShortcut: 'Control+Shift+J',
  pushToTalkKey: 'Space',
  requireRiskConfirmation: true,
  language: 'en',
};
