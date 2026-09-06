/** Ayar doğrulama/normalizasyon testleri. */

import { describe, expect, it } from 'vitest';

import {
  ARXIV_MCP_RECIPE,
  BRAVE_MCP_RECIPE,
  DEFAULT_SETTINGS,
  DUCKDUCKGO_MCP_RECIPE,
  GITHUB_MCP_RECIPE,
  HACKERNEWS_MCP_RECIPE,
  HUGGINGFACE_MCP_RECIPE,
  OPENLIBRARY_MCP_RECIPE,
  GEOCODE_MCP_RECIPE,
  MCP_RECIPE_CATALOG,
  MCP_SERVER_ENV_KEYS,
  RSS_MCP_RECIPE,
  TRANSLATE_MCP_RECIPE,
  PLAYWRIGHT_MCP_RECIPE,
  RECOMMENDED_MCP_SERVERS,
  WEATHER_MCP_RECIPE,
  WIKIDATA_MCP_RECIPE,
  WIKIPEDIA_MCP_RECIPE,
  YOUTUBE_MCP_RECIPE,
  applyRecommendedMcpServers,
  clearAllMcpServers,
  describeMcpServersJson,
  filterMcpRecipeCatalog,
  mcpSettingsFormDirty,
  parseMcpServersJson,
  MCP_FIRST_RUN_HINT,
  MCP_OVERLAP_SUMMARY,
  MCP_SERVERS_STORE_CAP,
  mcpNativeOverlapNote,
  keepRecommendedMcpServers,
  cloneMcpRecipeById,
  hasMcpServer,
  mergeMcpRecipe,
  mcpRecipeGroupActive,
  setMcpRecipeEnabled,
  setMcpRecipeGroupEnabled,
  setMcpServerEnvValue,
} from '@shared/settings';
import { sanitizeSettings } from '../electron/store';

describe('sanitizeSettings', () => {
  it('varsayılanları korur', () => {
    expect(sanitizeSettings({}, DEFAULT_SETTINGS)).toEqual(DEFAULT_SETTINGS);
  });

  it('geçersiz URL varsayılana döner', () => {
    const result = sanitizeSettings({ backendUrl: 'javascript:alert(1)' }, DEFAULT_SETTINGS);
    expect(result.backendUrl).toBe(DEFAULT_SETTINGS.backendUrl);
  });

  it('file: protokolünü reddeder', () => {
    const result = sanitizeSettings({ backendUrl: 'file:///etc/passwd' }, DEFAULT_SETTINGS);
    expect(result.backendUrl).toBe(DEFAULT_SETTINGS.backendUrl);
  });

  it('geçerli URL kabul edilir ve sondaki eğik çizgi silinir', () => {
    const result = sanitizeSettings({ backendUrl: 'http://127.0.0.1:9000/' }, DEFAULT_SETTINGS);
    expect(result.backendUrl).toBe('http://127.0.0.1:9000');
  });

  it('sayısal değerler aralığa sıkıştırılır', () => {
    const result = sanitizeSettings(
      { temperature: 99, gpuMemoryUtilization: 5, ragTopK: 1000, maxTokens: -10 },
      DEFAULT_SETTINGS,
    );
    expect(result.temperature).toBe(2);
    expect(result.gpuMemoryUtilization).toBe(0.98);
    expect(result.ragTopK).toBe(20);
    expect(result.maxTokens).toBe(64);
  });

  it('sayı olmayan değer varsayılana döner', () => {
    const result = sanitizeSettings(
      { temperature: 'çok sıcak' as unknown as number },
      DEFAULT_SETTINGS,
    );
    expect(result.temperature).toBe(0.7);
  });

  it('bilinmeyen tema varsayılana döner', () => {
    const result = sanitizeSettings({ theme: 'neon' as unknown as 'dark' }, DEFAULT_SETTINGS);
    expect(result.theme).toBe('dark');
  });

  it('açık ve sistem görünümü tek temada koyuya kilitlenir (D23)', () => {
    expect(sanitizeSettings({ theme: 'light' }, DEFAULT_SETTINGS).theme).toBe('dark');
    expect(sanitizeSettings({ theme: 'system' }, DEFAULT_SETTINGS).theme).toBe('dark');
  });

  it('vurgu paleti varsayılanı yeşil, mavi kabul, geçersiz yeşil', () => {
    expect(DEFAULT_SETTINGS.accentTheme).toBe('green');
    expect(sanitizeSettings({ accentTheme: 'blue' }, DEFAULT_SETTINGS).accentTheme).toBe('blue');
    expect(
      sanitizeSettings({ accentTheme: 'purple' as unknown as 'green' }, DEFAULT_SETTINGS)
        .accentTheme,
    ).toBe('green');
  });

  it('taze kurulum İngilizce; kayıtlı Türkçe durur; geçersiz varsayılana düşer', () => {
    expect(DEFAULT_SETTINGS.language).toBe('en');
    expect(sanitizeSettings({ language: 'en' }, DEFAULT_SETTINGS).language).toBe('en');
    expect(sanitizeSettings({ language: 'tr' }, DEFAULT_SETTINGS).language).toBe('tr');
    expect(sanitizeSettings({ language: 'de' as unknown as 'tr' }, DEFAULT_SETTINGS).language).toBe(
      'en',
    );
  });

  it('arayüz diline göre varsayılan cevap sesi değişir', () => {
    expect(DEFAULT_SETTINGS.ttsVoice).toBe('en-US-GuyNeural');
    expect(sanitizeSettings({ language: 'en' }, DEFAULT_SETTINGS).ttsVoice).toBe('en-US-GuyNeural');
    expect(sanitizeSettings({ language: 'tr' }, DEFAULT_SETTINGS).ttsVoice).toBe('tr-TR-AhmetNeural');
    expect(
      sanitizeSettings({ language: 'en', ttsVoice: 'tr-TR-AhmetNeural' }, DEFAULT_SETTINGS).ttsVoice,
    ).toBe('en-US-GuyNeural');
    expect(
      sanitizeSettings({ language: 'tr', ttsVoice: 'en-US-GuyNeural' }, DEFAULT_SETTINGS).ttsVoice,
    ).toBe('tr-TR-AhmetNeural');
    expect(
      sanitizeSettings({ language: 'en', ttsVoice: 'tr-TR-EmelNeural' }, DEFAULT_SETTINGS).ttsVoice,
    ).toBe('tr-TR-EmelNeural');
  });

  it('token uzunluğu sınırlanır', () => {
    const result = sanitizeSettings({ localToken: 'x'.repeat(500) }, DEFAULT_SETTINGS);
    expect(result.localToken).toHaveLength(256);
  });

  it("boolean olmayan değerler boolean'a çevrilir", () => {
    const result = sanitizeSettings(
      { ttsEnabled: 'evet' as unknown as boolean, ragEnabled: 0 as unknown as boolean },
      DEFAULT_SETTINGS,
    );
    expect(result.ttsEnabled).toBe(true);
    expect(result.ragEnabled).toBe(false);
  });

  it('bilinmeyen alanlar sonuca sızmaz', () => {
    const result = sanitizeSettings(
      { hackerField: 'payload' } as unknown as Partial<typeof DEFAULT_SETTINGS>,
      DEFAULT_SETTINGS,
    );
    expect('hackerField' in result).toBe(false);
  });

  it('wake word küçük harfe indirgenir', () => {
    const result = sanitizeSettings({ wakeWord: 'URYX' }, DEFAULT_SETTINGS);
    expect(result.wakeWord).toBe('uryx');
  });

  it('llmPreset model adından çıkarılır', () => {
    expect(
      sanitizeSettings({ llmPreset: 'balanced', modelName: 'qwen3-4b' }, DEFAULT_SETTINGS)
        .llmPreset,
    ).toBe('balanced');
    expect(sanitizeSettings({ modelName: 'qwen3-4b' }, DEFAULT_SETTINGS).llmPreset).toBe(
      'balanced',
    );
    expect(sanitizeSettings({ modelName: 'qwen3-4b-instruct' }, DEFAULT_SETTINGS).llmPreset).toBe(
      'balanced',
    );
    expect(sanitizeSettings({ modelName: 'qwen3-8b' }, DEFAULT_SETTINGS).llmPreset).toBe('quality');
    expect(sanitizeSettings({ modelName: 'qwen3.5-9b' }, DEFAULT_SETTINGS).llmPreset).toBe('agent');
    expect(DEFAULT_SETTINGS.llmPreset).toBe('quality');
    expect(DEFAULT_SETTINGS.modelName).toBe('qwen3-8b');
    expect(DEFAULT_SETTINGS.wakeWordEnabled).toBe(false);
  });

  it('eski ayar dosyalarında eksik yeni ses alanları varsayılana döner', () => {
    const legacy = {
      ...DEFAULT_SETTINGS,
      adaptiveVadEnabled: undefined,
      bargeInEnabled: undefined,
    } as unknown as typeof DEFAULT_SETTINGS;
    const result = sanitizeSettings({}, legacy);
    expect(result.adaptiveVadEnabled).toBe(true);
    expect(result.bargeInEnabled).toBe(false);
  });

  it('Win/Super kısayolunu reddeder, Control+Shift kabul eder', () => {
    expect(sanitizeSettings({ globalShortcut: 'Super+L' }, DEFAULT_SETTINGS).globalShortcut).toBe(
      DEFAULT_SETTINGS.globalShortcut,
    );
    expect(sanitizeSettings({ globalShortcut: 'Win+R' }, DEFAULT_SETTINGS).globalShortcut).toBe(
      DEFAULT_SETTINGS.globalShortcut,
    );
    expect(
      sanitizeSettings({ globalShortcut: 'Control+Shift+K' }, DEFAULT_SETTINGS).globalShortcut,
    ).toBe('Control+Shift+K');
    expect(sanitizeSettings({ pushToTalkKey: 'Super' }, DEFAULT_SETTINGS).pushToTalkKey).toBe(
      DEFAULT_SETTINGS.pushToTalkKey,
    );
  });

  it('MCP sunucusunda kabuk komutunu ve tehlikeli argümanı eler', () => {
    const result = sanitizeSettings(
      {
        mcpEnabled: true,
        mcpServers: [
          {
            id: 'spotify',
            command: 'npx',
            args: ['-y', '@spotify/mcp'],
            allowedTools: ['search'],
          },
          {
            id: 'shell',
            command: 'powershell.exe',
            args: ['-Command', 'calc'],
            allowedTools: ['run'],
          },
        ],
      },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([
      {
        id: 'spotify',
        command: 'npx',
        args: ['-y', '@spotify/mcp'],
        allowedTools: ['search'],
      },
    ]);
  });

  it('MCP -c ve --eval argümanını kayıttan düşürür', () => {
    const result = sanitizeSettings(
      {
        mcpEnabled: true,
        mcpServers: [
          {
            id: 'docs',
            command: 'npx',
            args: ['-y', '-c', 'calc', 'pkg'],
            allowedTools: ['query-docs'],
          },
        ],
      },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers[0]?.args).toEqual(['-y', 'pkg']);
  });

  it('MCP env yalnızca allowlist anahtarlarını tutar', () => {
    const result = sanitizeSettings(
      {
        mcpEnabled: true,
        mcpServers: [
          {
            id: 'docs',
            command: 'npx',
            args: ['-y', '@upstash/context7-mcp'],
            allowedTools: ['resolve-library-id'],
            env: {
              CONTEXT7_API_KEY: 'ctx7sk_test',
              NODE_OPTIONS: '--inspect',
              GH_TOKEN: 'ghs_nope',
            },
          },
        ],
      },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([
      {
        id: 'docs',
        command: 'npx',
        args: ['-y', '@upstash/context7-mcp'],
        allowedTools: ['resolve-library-id'],
        env: { CONTEXT7_API_KEY: 'ctx7sk_test' },
      },
    ]);
  });

  it('önerilen MCP katalogu allowlist komutları ve araç adları kullanır', () => {
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: RECOMMENDED_MCP_SERVERS },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers.map((server) => server.id)).toEqual(['fetch', 'time', 'docs', 'think']);
    expect(result.mcpServers).toHaveLength(RECOMMENDED_MCP_SERVERS.length);
  });

  it('Playwright tarif kartı önerilen katalogda yoktur ve allowlist komut kullanır', () => {
    expect(RECOMMENDED_MCP_SERVERS.map((server) => server.id)).not.toContain('playwright');
    expect(PLAYWRIGHT_MCP_RECIPE.id).toBe('playwright');
    expect(PLAYWRIGHT_MCP_RECIPE.command).toBe('npx');
    expect(PLAYWRIGHT_MCP_RECIPE.args).toContain('@playwright/mcp');
    expect(PLAYWRIGHT_MCP_RECIPE.allowedTools).toContain('browser_snapshot');
    expect(PLAYWRIGHT_MCP_RECIPE.allowedTools).not.toContain('browser_click');
    expect(PLAYWRIGHT_MCP_RECIPE.allowedTools).not.toContain('browser_type');
    expect(PLAYWRIGHT_MCP_RECIPE.allowedTools).not.toContain('browser_evaluate');
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [PLAYWRIGHT_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([PLAYWRIGHT_MCP_RECIPE]);
  });

  it('önerilen katalog Playwright tarifini silmez', () => {
    const merged = mergeMcpRecipe(RECOMMENDED_MCP_SERVERS, PLAYWRIGHT_MCP_RECIPE);
    const kept = applyRecommendedMcpServers(merged);
    expect(kept.map((server) => server.id)).toEqual([
      'fetch',
      'time',
      'docs',
      'think',
      'playwright',
    ]);
  });

  it('GitHub tarif kartı önerilen katalogda yoktur, npx kullanır, docker yok', () => {
    expect(RECOMMENDED_MCP_SERVERS.map((server) => server.id)).not.toContain('github');
    expect(GITHUB_MCP_RECIPE.id).toBe('github');
    expect(GITHUB_MCP_RECIPE.command).toBe('npx');
    expect(GITHUB_MCP_RECIPE.args).toContain('@modelcontextprotocol/server-github');
    expect(GITHUB_MCP_RECIPE.args.join(' ')).not.toMatch(/docker/i);
    expect(GITHUB_MCP_RECIPE.allowedTools).toContain('search_repositories');
    expect(GITHUB_MCP_RECIPE.allowedTools).toContain('get_file_contents');
    expect(GITHUB_MCP_RECIPE.allowedTools).not.toContain('create_or_update_file');
    expect(GITHUB_MCP_RECIPE.allowedTools).not.toContain('push_files');
    expect(GITHUB_MCP_RECIPE.allowedTools).not.toContain('merge_pull_request');
    expect(GITHUB_MCP_RECIPE.env).toBeUndefined();
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [GITHUB_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([GITHUB_MCP_RECIPE]);
  });

  it('önerilen katalog GitHub tarifini silmez ve PAT env allowlist geçer', () => {
    const withPat = {
      ...GITHUB_MCP_RECIPE,
      env: { GITHUB_PERSONAL_ACCESS_TOKEN: 'ghp_local_only' },
    };
    const merged = mergeMcpRecipe(
      mergeMcpRecipe(RECOMMENDED_MCP_SERVERS, PLAYWRIGHT_MCP_RECIPE),
      withPat,
    );
    const kept = applyRecommendedMcpServers(merged);
    expect(kept.map((server) => server.id)).toEqual([
      'fetch',
      'time',
      'docs',
      'think',
      'playwright',
      'github',
    ]);
    const result = sanitizeSettings({ mcpEnabled: true, mcpServers: [withPat] }, DEFAULT_SETTINGS);
    expect(result.mcpServers[0]?.env).toEqual({
      GITHUB_PERSONAL_ACCESS_TOKEN: 'ghp_local_only',
    });
  });

  it('Brave tarif kartı npx resmi pakettir, HTTP transport yok', () => {
    expect(RECOMMENDED_MCP_SERVERS.map((server) => server.id)).not.toContain('brave');
    expect(BRAVE_MCP_RECIPE.command).toBe('npx');
    expect(BRAVE_MCP_RECIPE.args).toContain('@brave/brave-search-mcp-server');
    expect(BRAVE_MCP_RECIPE.args.join(' ')).not.toMatch(/docker|http/i);
    expect(BRAVE_MCP_RECIPE.allowedTools).toContain('brave_web_search');
    expect(BRAVE_MCP_RECIPE.allowedTools).not.toContain('brave_image_search');
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [BRAVE_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([BRAVE_MCP_RECIPE]);
  });

  it('Hugging Face tarif kartı stdio npx, iş/fs araçları yok', () => {
    expect(HUGGINGFACE_MCP_RECIPE.command).toBe('npx');
    expect(HUGGINGFACE_MCP_RECIPE.args).toContain('@llmindset/hf-mcp-server');
    expect(HUGGINGFACE_MCP_RECIPE.args.join(' ')).not.toMatch(/docker/i);
    expect(HUGGINGFACE_MCP_RECIPE.allowedTools).toContain('model_search');
    expect(HUGGINGFACE_MCP_RECIPE.allowedTools).not.toContain('hf_jobs');
    expect(HUGGINGFACE_MCP_RECIPE.allowedTools).not.toContain('hf_fs');
    expect(HUGGINGFACE_MCP_RECIPE.allowedTools).not.toContain('dynamic_space');
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [HUGGINGFACE_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([HUGGINGFACE_MCP_RECIPE]);
  });

  it('Hava tarif kartı uvx stdio, http argümanı yok', () => {
    expect(WEATHER_MCP_RECIPE.command).toBe('uvx');
    expect(WEATHER_MCP_RECIPE.args).toEqual(['chuk-mcp-open-meteo']);
    expect(WEATHER_MCP_RECIPE.args.join(' ')).not.toMatch(/docker|\bhttp\b/i);
    expect(WEATHER_MCP_RECIPE.allowedTools).toContain('get_weather_forecast');
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [WEATHER_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([WEATHER_MCP_RECIPE]);
  });

  it('kart yardımcısı tarif açar/kapatır ve env korur', () => {
    const withBrave = setMcpRecipeEnabled(RECOMMENDED_MCP_SERVERS, BRAVE_MCP_RECIPE, true);
    expect(hasMcpServer(withBrave, 'brave')).toBe(true);
    const withKey = setMcpServerEnvValue(withBrave, 'brave', 'BRAVE_API_KEY', 'BSA_local');
    expect(withKey.find((server) => server.id === 'brave')?.env).toEqual({
      BRAVE_API_KEY: 'BSA_local',
    });
    const reapplied = setMcpRecipeEnabled(withKey, cloneMcpRecipeById('brave')!, true);
    expect(reapplied.find((server) => server.id === 'brave')?.env).toEqual({
      BRAVE_API_KEY: 'BSA_local',
    });
    const off = setMcpRecipeEnabled(withKey, BRAVE_MCP_RECIPE, false);
    expect(hasMcpServer(off, 'brave')).toBe(false);
  });

  it('önerilen katalog Brave/HF/hava tariflerini silmez', () => {
    const merged = [
      PLAYWRIGHT_MCP_RECIPE,
      GITHUB_MCP_RECIPE,
      BRAVE_MCP_RECIPE,
      HUGGINGFACE_MCP_RECIPE,
      WEATHER_MCP_RECIPE,
      WIKIPEDIA_MCP_RECIPE,
      ARXIV_MCP_RECIPE,
      WIKIDATA_MCP_RECIPE,
      YOUTUBE_MCP_RECIPE,
      HACKERNEWS_MCP_RECIPE,
      DUCKDUCKGO_MCP_RECIPE,
      OPENLIBRARY_MCP_RECIPE,
      TRANSLATE_MCP_RECIPE,
      RSS_MCP_RECIPE,
      GEOCODE_MCP_RECIPE,
    ].reduce(
      (servers, recipe) => mergeMcpRecipe(servers, recipe),
      [...RECOMMENDED_MCP_SERVERS],
    );
    const kept = applyRecommendedMcpServers(merged);
    expect(kept.map((server) => server.id)).toEqual([
      'fetch',
      'time',
      'docs',
      'think',
      'playwright',
      'github',
      'brave',
      'huggingface',
      'weather',
      'wikipedia',
      'arxiv',
      'wikidata',
      'youtube',
      'hn',
      'ddg',
      'openlibrary',
      'translate',
      'rss',
      'geocode',
    ]);
  });

  it('Wikipedia tarif kartı npx salt okuma, docker/http yok', () => {
    expect(WIKIPEDIA_MCP_RECIPE.command).toBe('npx');
    expect(WIKIPEDIA_MCP_RECIPE.args).toContain('@cyanheads/wikipedia-mcp-server');
    expect(WIKIPEDIA_MCP_RECIPE.args.join(' ')).not.toMatch(/docker|http/i);
    expect(WIKIPEDIA_MCP_RECIPE.allowedTools).toContain('wikipedia_search');
    expect(WIKIPEDIA_MCP_RECIPE.allowedTools).toContain('wikipedia_get_summary');
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [WIKIPEDIA_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([WIKIPEDIA_MCP_RECIPE]);
  });

  it('arXiv tarif kartı uvx, indirme ve yerel kağıt yok', () => {
    expect(ARXIV_MCP_RECIPE.command).toBe('uvx');
    expect(ARXIV_MCP_RECIPE.args).toEqual(['arxiv-mcp-server']);
    expect(ARXIV_MCP_RECIPE.allowedTools).toContain('search_papers');
    expect(ARXIV_MCP_RECIPE.allowedTools).toContain('get_abstract');
    expect(ARXIV_MCP_RECIPE.allowedTools).not.toContain('download_paper');
    expect(ARXIV_MCP_RECIPE.allowedTools).not.toContain('read_paper');
    expect(ARXIV_MCP_RECIPE.allowedTools).not.toContain('list_papers');
    expect(ARXIV_MCP_RECIPE.allowedTools).not.toContain('watch_topic');
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [ARXIV_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([ARXIV_MCP_RECIPE]);
  });

  it('ek tarifleri kapat boş listede önerilen dördü basar', () => {
    expect(keepRecommendedMcpServers([]).map((server) => server.id)).toEqual([
      'fetch',
      'time',
      'docs',
      'think',
    ]);
  });

  it('ek tarifleri kapat yalnızca önerilen dördü bırakır', () => {
    const mixed = mergeMcpRecipe(
      mergeMcpRecipe(RECOMMENDED_MCP_SERVERS, BRAVE_MCP_RECIPE),
      WIKIDATA_MCP_RECIPE,
    );
    expect(keepRecommendedMcpServers(mixed).map((server) => server.id)).toEqual([
      'fetch',
      'time',
      'docs',
      'think',
    ]);
  });

  it('Wikidata tarif kartı npx salt okuma, docker/http yok', () => {
    expect(WIKIDATA_MCP_RECIPE.command).toBe('npx');
    expect(WIKIDATA_MCP_RECIPE.args).toContain('@cyanheads/wikidata-mcp-server');
    expect(WIKIDATA_MCP_RECIPE.args.join(' ')).not.toMatch(/docker|http/i);
    expect(WIKIDATA_MCP_RECIPE.allowedTools).toContain('wikidata_search_entities');
    expect(WIKIDATA_MCP_RECIPE.allowedTools).toContain('wikidata_sparql_query');
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [WIKIDATA_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers).toEqual([WIKIDATA_MCP_RECIPE]);
  });

  it('tüm katalog tarifleri birlikte sanitize olur, docker yok', () => {
    const all = MCP_RECIPE_CATALOG.map((card) => cloneMcpRecipeById(card.id)!);
    expect(all).toHaveLength(MCP_RECIPE_CATALOG.length);
    for (const recipe of all) {
      expect(recipe.args.join(' ')).not.toMatch(/docker/i);
      expect(['npx', 'uvx']).toContain(recipe.command);
    }
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: all },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers.map((server) => server.id)).toEqual(
      MCP_RECIPE_CATALOG.map((card) => card.id),
    );
  });

  it('katalog kimlikleri tariflerle örtüşür ve env anahtarları allowlisttedir', () => {
    expect(MCP_RECIPE_CATALOG.map((card) => card.id)).toEqual([
      'fetch',
      'time',
      'docs',
      'think',
      'playwright',
      'github',
      'brave',
      'huggingface',
      'weather',
      'wikipedia',
      'arxiv',
      'wikidata',
      'youtube',
      'hn',
      'ddg',
      'openlibrary',
      'translate',
      'rss',
      'geocode',
    ]);
    for (const card of MCP_RECIPE_CATALOG) {
      expect(cloneMcpRecipeById(card.id)?.id).toBe(card.id);
      expect(['recommended', 'code', 'search', 'knowledge']).toContain(card.group);
      for (const field of card.env ?? []) {
        expect(MCP_SERVER_ENV_KEYS).toContain(field.key);
      }
    }
  });

  it('BRAVE_API_KEY ve HF_TOKEN allowlist geçer, süreç sızıntısı yok', () => {
    const result = sanitizeSettings(
      {
        mcpEnabled: true,
        mcpServers: [
          {
            ...BRAVE_MCP_RECIPE,
            env: { BRAVE_API_KEY: 'BSA_ok', NODE_OPTIONS: '--inspect', GH_TOKEN: 'nope' },
          },
          {
            ...HUGGINGFACE_MCP_RECIPE,
            env: { HF_TOKEN: 'hf_ok', AWS_SECRET_ACCESS_KEY: 'nope' },
          },
        ],
      },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers[0]?.env).toEqual({ BRAVE_API_KEY: 'BSA_ok' });
    expect(result.mcpServers[1]?.env).toEqual({ HF_TOKEN: 'hf_ok' });
  });

  it('YouTube tarif kartı uvx PyPI, git+ ve docker yok', () => {
    expect(YOUTUBE_MCP_RECIPE.command).toBe('uvx');
    expect(YOUTUBE_MCP_RECIPE.args).toEqual(['mcp-youtube-transcript']);
    expect(YOUTUBE_MCP_RECIPE.args.join(' ')).not.toMatch(/docker|git\+/i);
    expect(YOUTUBE_MCP_RECIPE.allowedTools).toContain('get_transcript');
    expect(sanitizeSettings({ mcpEnabled: true, mcpServers: [YOUTUBE_MCP_RECIPE] }, DEFAULT_SETTINGS).mcpServers).toEqual(
      [YOUTUBE_MCP_RECIPE],
    );
  });

  it('Hacker News tarif kartı npx salt okuma', () => {
    expect(HACKERNEWS_MCP_RECIPE.command).toBe('npx');
    expect(HACKERNEWS_MCP_RECIPE.args).toContain('@cyanheads/hn-mcp-server');
    expect(HACKERNEWS_MCP_RECIPE.allowedTools).toContain('hn_get_stories');
    expect(HACKERNEWS_MCP_RECIPE.allowedTools).toContain('hn_search_content');
    expect(sanitizeSettings({ mcpEnabled: true, mcpServers: [HACKERNEWS_MCP_RECIPE] }, DEFAULT_SETTINGS).mcpServers).toEqual(
      [HACKERNEWS_MCP_RECIPE],
    );
  });

  it('DuckDuckGo yalnız search, tr-tr bölge, fetch_content yok', () => {
    expect(DUCKDUCKGO_MCP_RECIPE.command).toBe('uvx');
    expect(DUCKDUCKGO_MCP_RECIPE.allowedTools).toEqual(['search']);
    expect(DUCKDUCKGO_MCP_RECIPE.allowedTools).not.toContain('fetch_content');
    expect(DUCKDUCKGO_MCP_RECIPE.env).toEqual({ DDG_REGION: 'tr-tr', DDG_SAFE_SEARCH: 'MODERATE' });
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [DUCKDUCKGO_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers[0]?.env).toEqual({ DDG_REGION: 'tr-tr', DDG_SAFE_SEARCH: 'MODERATE' });
  });

  it('Open Library tarif kartı npx salt okuma, docker yok', () => {
    expect(OPENLIBRARY_MCP_RECIPE.command).toBe('npx');
    expect(OPENLIBRARY_MCP_RECIPE.args).toContain('@cyanheads/openlibrary-mcp-server');
    expect(OPENLIBRARY_MCP_RECIPE.allowedTools).toContain('openlibrary_search_books');
    expect(OPENLIBRARY_MCP_RECIPE.allowedTools).toContain('openlibrary_get_edition');
    expect(sanitizeSettings({ mcpEnabled: true, mcpServers: [OPENLIBRARY_MCP_RECIPE] }, DEFAULT_SETTINGS).mcpServers).toEqual(
      [OPENLIBRARY_MCP_RECIPE],
    );
  });

  it('LibreTranslate tarif kartı npx, docker yok, URL env kalır', () => {
    expect(TRANSLATE_MCP_RECIPE.command).toBe('npx');
    expect(TRANSLATE_MCP_RECIPE.args).toContain('@libretranslate/mcp');
    expect(TRANSLATE_MCP_RECIPE.args.join(' ')).not.toMatch(/docker/i);
    expect(TRANSLATE_MCP_RECIPE.allowedTools).toEqual(['detect', 'translate', 'languages']);
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [TRANSLATE_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers[0]?.env).toEqual({
      LIBRETRANSLATE_API_URL: 'https://libretranslate.com',
    });
  });

  it('RSS tarif kartı npx get_feed, yerel yazma yok', () => {
    expect(RSS_MCP_RECIPE.command).toBe('npx');
    expect(RSS_MCP_RECIPE.args).toEqual(['-y', 'rss-mcp']);
    expect(RSS_MCP_RECIPE.allowedTools).toEqual(['get_feed']);
    expect(RSS_MCP_RECIPE.args.join(' ')).not.toMatch(/docker|rss-feeds-mcp/i);
    expect(
      sanitizeSettings({ mcpEnabled: true, mcpServers: [RSS_MCP_RECIPE] }, DEFAULT_SETTINGS)
        .mcpServers,
    ).toEqual([RSS_MCP_RECIPE]);
  });

  it('OSM geocode tarif kartı npx, ham Overpass yok', () => {
    expect(GEOCODE_MCP_RECIPE.command).toBe('npx');
    expect(GEOCODE_MCP_RECIPE.args).toContain('geocode-mcp');
    expect(GEOCODE_MCP_RECIPE.allowedTools).toContain('geocode');
    expect(GEOCODE_MCP_RECIPE.allowedTools).toContain('reverse_geocode');
    expect(GEOCODE_MCP_RECIPE.allowedTools).not.toContain('openstreetmap_query_raw');
    const result = sanitizeSettings(
      { mcpEnabled: true, mcpServers: [GEOCODE_MCP_RECIPE] },
      DEFAULT_SETTINGS,
    );
    expect(result.mcpServers[0]?.env).toEqual({ GEOCODE_USER_AGENT: 'Uryx local assistant' });
  });

  it('katalog araması Türkçe başlık ve kimlikle süzülür', () => {
    expect(filterMcpRecipeCatalog(MCP_RECIPE_CATALOG, 'çeviri').map((card) => card.id)).toEqual([
      'translate',
    ]);
    expect(filterMcpRecipeCatalog(MCP_RECIPE_CATALOG, 'RSS').map((card) => card.id)).toEqual(['rss']);
    expect(filterMcpRecipeCatalog(MCP_RECIPE_CATALOG, 'nominatim').map((card) => card.id)).toEqual([
      'geocode',
    ]);
    expect(filterMcpRecipeCatalog(MCP_RECIPE_CATALOG, '  ').map((card) => card.id)).toEqual(
      MCP_RECIPE_CATALOG.map((card) => card.id),
    );
  });

  it('grup kapat/aç yalnız o kategoriyi değiştirir ve env korur', () => {
    const withKey = setMcpServerEnvValue(
      mergeMcpRecipe(RECOMMENDED_MCP_SERVERS, BRAVE_MCP_RECIPE),
      'brave',
      'BRAVE_API_KEY',
      'BSA_keep',
    );
    const closed = setMcpRecipeGroupEnabled(withKey, 'search', false);
    expect(hasMcpServer(closed, 'brave')).toBe(false);
    expect(closed.map((server) => server.id)).toEqual(['fetch', 'time', 'docs', 'think']);
    const opened = setMcpRecipeGroupEnabled(closed, 'search', true);
    expect(mcpRecipeGroupActive(opened, 'search')).toBe(true);
    expect(hasMcpServer(opened, 'brave')).toBe(true);
    expect(hasMcpServer(opened, 'rss')).toBe(true);
    expect(hasMcpServer(opened, 'ddg')).toBe(true);
    const reopened = setMcpRecipeGroupEnabled(withKey, 'search', true);
    expect(reopened.find((server) => server.id === 'brave')?.env).toEqual({
      BRAVE_API_KEY: 'BSA_keep',
    });
  });

  it('tüm sunucuları kapat boş liste döner; JSON doğrulama hata verir', () => {
    expect(clearAllMcpServers()).toEqual([]);
    expect(describeMcpServersJson('[]')).toEqual({ ok: true, count: 0 });
    expect(describeMcpServersJson('{', 'tr')).toEqual({ ok: false, error: 'MCP sunucu JSON’u geçersiz.' });
    expect(describeMcpServersJson('{}', 'tr')).toEqual({ ok: false, error: 'MCP listesi dizi olmalı.' });
  });

  it('geçersiz tarif JSON’unu kayıttan önce reddeder', () => {
    expect(describeMcpServersJson('[{}]', 'tr').ok).toBe(false);
    expect(describeMcpServersJson('[{"id":"x","command":"docker"}]', 'tr').error).toMatch(/allowlist/);
    expect(
      describeMcpServersJson(
        '[{"id":"docs","command":"npx"},{"id":"docs","command":"uvx"}]',
        'tr',
      ).error,
    ).toMatch(/tekrar/);
    expect(describeMcpServersJson('[null]', 'tr').error).toMatch(/nesne/);
    expect(describeMcpServersJson('[{"id":"docs","command":"npx","args":"-y"}]', 'tr').error).toMatch(
      /args/,
    );
    expect(parseMcpServersJson('[{"id":"docs","command":"npx","args":["-y"]}]')).toEqual([
      { id: 'docs', command: 'npx', args: ['-y'] },
    ]);
    expect(parseMcpServersJson('[{"id":"x","command":"cmd.exe"}]')).toBeNull();
    expect(describeMcpServersJson('[{"id":"docs","command":"./npx.cmd"}]', 'tr').error).toMatch(
      /allowlist/,
    );
    expect(
      describeMcpServersJson('[{"id":"docs","command":"C:\\\\foo\\\\..\\\\npx.cmd"}]', 'tr').error,
    ).toMatch(/allowlist/);
    expect(describeMcpServersJson('[{"id":"docs","command":"C:npx"}]', 'tr').error).toMatch(/allowlist/);
  });

  it('yerleşik araç çakışma metni DDG/hava/wiki/fx anlatır, Frankfurter yok', () => {
    expect(MCP_RECIPE_CATALOG).toHaveLength(19);
    expect(MCP_RECIPE_CATALOG.length).toBeLessThanOrEqual(MCP_SERVERS_STORE_CAP);
    expect(MCP_RECIPE_CATALOG.map((card) => card.id)).not.toContain('frankfurter');
    expect(MCP_OVERLAP_SUMMARY).toMatch(/web_search/);
    expect(MCP_OVERLAP_SUMMARY).toMatch(/wiki_lookup/);
    expect(MCP_OVERLAP_SUMMARY).toMatch(/fx_rate/);
    expect(MCP_OVERLAP_SUMMARY).toMatch(/Frankfurter MCP yok/);
    expect(mcpNativeOverlapNote('ddg')).toMatch(/web_search/);
    expect(mcpNativeOverlapNote('weather')).toMatch(/\bweather\b/);
    expect(mcpNativeOverlapNote('wikipedia')).toMatch(/wiki_lookup/);
    expect(mcpNativeOverlapNote('fx')).toMatch(/fx_rate/);
    expect(MCP_RECIPE_CATALOG.find((card) => card.id === 'ddg')?.description).toMatch(/web_search/);
    expect(MCP_RECIPE_CATALOG.find((card) => card.id === 'weather')?.description).toMatch(/weather/);
    expect(MCP_RECIPE_CATALOG.find((card) => card.id === 'wikipedia')?.description).toMatch(
      /wiki_lookup/,
    );
    expect(MCP_FIRST_RUN_HINT).toMatch(/40 sn/);
  });

  it('store tavanı 20; fazlası düşer ve JSON uyarı verir', () => {
    const extra = Array.from({ length: MCP_SERVERS_STORE_CAP + 1 }, (_, index) => ({
      id: `extra${index}`,
      command: 'npx',
      args: ['-y', 'pkg'],
      allowedTools: ['ping'],
    }));
    const result = sanitizeSettings({ mcpEnabled: true, mcpServers: extra }, DEFAULT_SETTINGS);
    expect(result.mcpServers).toHaveLength(MCP_SERVERS_STORE_CAP);
    const described = describeMcpServersJson(JSON.stringify(extra), 'tr');
    expect(described).toMatchObject({
      ok: true,
      count: MCP_SERVERS_STORE_CAP + 1,
      hint: `En fazla ${MCP_SERVERS_STORE_CAP} sunucu kaydedilir; fazlası düşer.`,
    });
  });

  it('gelişmiş JSON taslağı kayıttan farklıysa form kirli', () => {
    const saved = [{ id: 'docs', command: 'npx', args: ['-y', 'pkg'], allowedTools: ['query-docs'] }];
    expect(mcpSettingsFormDirty(saved, JSON.stringify(saved, null, 2))).toBe(false);
    expect(mcpSettingsFormDirty(saved, '[]')).toBe(true);
    expect(mcpSettingsFormDirty(saved, '{')).toBe(true);
  });
});
