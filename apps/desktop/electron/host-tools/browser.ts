/** Uryx'in kalıcı ve kısıtlı web tarayıcısı. */

import { app, BrowserWindow, shell } from 'electron';
import { mkdir, writeFile } from 'node:fs/promises';
import { isIP } from 'node:net';
import path from 'node:path';

import { resolveAppIconPath } from '../app-icon';
import { hostText } from '../host-i18n';
import { sanitizeSingleLine } from '../security';

const BROWSER_PARTITION = 'persist:uryx-browser';
const MAX_PAGE_TEXT = 12_000;
const MAX_MEDIA_BYTES = 15 * 1024 * 1024;
const MAX_MEDIA_RESULTS = 10;

let browserWindow: BrowserWindow | null = null;

interface PageImage {
  url: string;
  alt: string;
  width: number;
  height: number;
}

export interface PageControl {
  index: number;
  tag: string;
  type: string;
  role: string;
  name: string;
  href: string | null;
}

interface PageState {
  title: string;
  url: string;
  text: string;
  links: Array<{ text: string; url: string }>;
  images: PageImage[];
  controls: PageControl[];
}

/** Yalnızca genel HTTP(S) adreslerine izin verir. */
export function normalizePublicWebUrl(value: unknown): string {
  const raw = sanitizeSingleLine(value, 2048);
  if (!raw) throw new Error(hostText('Açılacak web adresi gerekli.', 'A web address is required.'));
  const explicitScheme = raw.match(/^([a-z][a-z0-9+.-]*):/i)?.[1]?.toLowerCase();
  if (explicitScheme && !['http', 'https'].includes(explicitScheme)) {
    throw new Error(
      hostText('Yalnızca HTTP ve HTTPS web adresleri açılabilir.', 'Only HTTP and HTTPS web addresses can be opened.'),
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
  } catch {
    throw new Error(hostText('Geçerli bir web adresi gerekli.', 'A valid web address is required.'));
  }

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(
      hostText('Yalnızca HTTP ve HTTPS web adresleri açılabilir.', 'Only HTTP and HTTPS web addresses can be opened.'),
    );
  }
  if (parsed.username || parsed.password) {
    throw new Error(
      hostText(
        'Kullanıcı bilgisi içeren web adresleri açılamaz.',
        'Web addresses that contain user info cannot be opened.',
      ),
    );
  }
  if (isPrivateHostname(parsed.hostname)) {
    throw new Error(
      hostText(
        'Yerel veya özel ağ adresleri Uryx Web içinde açılamaz.',
        'Local or private network addresses cannot be opened in Uryx Web.',
      ),
    );
  }

  parsed.hash = parsed.hash.slice(0, 500);
  return parsed.toString();
}

/** `open_external_url` — varsayılan tarayıcı; Uryx Web oturumu değil. */
export async function openExternalUrl(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const url = normalizePublicWebUrl(args.url);
  await shell.openExternal(url);
  return { opened: true, url };
}

/** `browser_open` aracı. */
export async function openBrowserPage(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const url = normalizePublicWebUrl(args.url);
  const waitMs = clamp(Number(args.wait_ms ?? 2500), 500, 10_000);
  const visible = args.visible !== false;
  const window = ensureBrowserWindow();

  if (visible) {
    window.show();
    window.focus();
  } else {
    window.hide();
  }
  await withTimeout(
    window.loadURL(url),
    35_000,
    hostText('Web sayfası zaman aşımına uğradı.', 'The web page timed out.'),
  );
  await delay(waitMs);

  const state = await collectPageState(window);
  const loginRequired = isBrowserLoginWall(state.url, state.title, state.text);
  if (loginRequired && !window.isVisible()) {
    window.show();
    window.focus();
  }
  return summarizeState(state, {
    opened: true,
    visible: visible || loginRequired,
    persistent_session: true,
  });
}

/** `browser_read_page` aracı. */
export async function readBrowserPage(): Promise<Record<string, unknown>> {
  const window = requireBrowserWindow();
  return summarizeState(await collectPageState(window), { read: true });
}

/** `browser_list_controls` — collectPageState sarmalayıcısı; private fonksiyon kayıtlı değil. */
export async function listBrowserControls(): Promise<Record<string, unknown>> {
  const window = requireBrowserWindow();
  const state = await collectPageState(window);
  return {
    title: state.title,
    url: state.url,
    controls: state.controls,
    count: state.controls.length,
  };
}

function controlSignature(control: PageControl): string {
  return `${control.tag}|${control.type}|${control.role}|${control.name}`;
}

export function resolveBrowserControl(
  controls: PageControl[],
  args: Record<string, unknown>,
): PageControl {
  const indexRaw = args.index;
  if (indexRaw !== undefined && indexRaw !== null && String(indexRaw).trim() !== '') {
    const index = Number(indexRaw);
    if (!Number.isInteger(index) || index < 0 || index >= controls.length) {
      throw new Error('stale_snapshot');
    }
    return controls[index];
  }
  const role = sanitizeSingleLine(args.role ?? '', 40).toLowerCase();
  const name = sanitizeSingleLine(args.name ?? '', 120).toLowerCase();
  if (!role && !name) {
    throw new Error(
      hostText('Kontrol indeksi veya rol+ad gerekli.', 'A control index or role+name is required.'),
    );
  }
  const match = controls.find(
    (control) =>
      (!role || control.role === role) && (!name || control.name.toLowerCase() === name),
  );
  if (!match) throw new Error('stale_snapshot');
  return match;
}

export function rejectPasswordControl(type: string): void {
  if (type === 'password') {
    throw new Error(hostText('Şifre alanına yazılamaz.', 'Cannot type into a password field.'));
  }
}

function resolveControl(state: PageState, args: Record<string, unknown>): PageControl {
  return resolveBrowserControl(state.controls, args);
}

async function assertSamePublicOrigin(window: BrowserWindow, expectedUrl: string): Promise<void> {
  const live = normalizePublicWebUrl(window.webContents.getURL());
  const expected = normalizePublicWebUrl(expectedUrl);
  if (new URL(live).origin !== new URL(expected).origin) {
    throw new Error('stale_snapshot');
  }
}

const CONTROL_ACTION_IIFE = `(payload) => {
  const clean = (value, limit) => String(value || '').replace(/\\s+/g, ' ').trim().slice(0, limit);
  const visible = (element) => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return rect.width > 1 && rect.height > 1 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const nodes = Array.from(document.querySelectorAll(
    'a[href], button, input, textarea, select, [role="button"], [role="textbox"], [role="link"], [contenteditable="true"]',
  )).filter(visible).slice(0, 80);
  const element = nodes[payload.index];
  if (!element) return { ok: false, reason: 'stale_snapshot' };
  const type = clean(element.getAttribute('type'), 40).toLowerCase();
  const signature = [
    String(element.tagName || '').toLowerCase(),
    type,
    clean(element.getAttribute('role') || element.tagName, 40).toLowerCase(),
    clean(
      element.getAttribute('aria-label') ||
        element.getAttribute('placeholder') ||
        element.getAttribute('name') ||
        element.innerText,
      120,
    ),
  ].join('|');
  if (payload.signature && signature !== payload.signature) return { ok: false, reason: 'stale_snapshot' };
  if (type === 'password') return { ok: false, reason: 'password_blocked' };
  if (payload.action === 'click') {
    element.click();
    return { ok: true, url: location.href };
  }
  if (payload.action === 'type') {
    const text = String(payload.text || '').slice(0, 500);
    element.focus();
    if ('value' in element) {
      const proto = Object.getOwnPropertyDescriptor(element.constructor.prototype, 'value');
      if (proto && proto.set) proto.set.call(element, text);
      else element.value = text;
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      element.textContent = text;
      element.dispatchEvent(new Event('input', { bubbles: true }));
    }
    return { ok: true, url: location.href };
  }
  return { ok: false, reason: 'unknown_action' };
}`;

async function runControlAction(
  window: BrowserWindow,
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const result = (await window.webContents.executeJavaScript(
    `(${CONTROL_ACTION_IIFE})(${JSON.stringify(payload)})`,
    true,
  )) as { ok?: boolean; reason?: string; url?: string };
  if (!result?.ok) {
    const reason = result?.reason || 'stale_snapshot';
    if (reason === 'password_blocked') {
      throw new Error(hostText('Şifre alanına yazılamaz.', 'Cannot type into a password field.'));
    }
    throw new Error(reason);
  }
  return { ok: true, url: typeof result.url === 'string' ? result.url : window.webContents.getURL() };
}

/** `browser_click` — sabit IIFE, CSS/x-y yok. */
export async function clickBrowserControl(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const window = requireBrowserWindow();
  const state = await collectPageState(window);
  await assertSamePublicOrigin(window, state.url);
  const control = resolveControl(state, args);
  const result = await runControlAction(window, {
    action: 'click',
    index: control.index,
    signature: controlSignature(control),
  });
  return { clicked: true, index: control.index, url: result.url };
}

/** `browser_type` — password blok; en fazla 500 karakter. */
export async function typeBrowserControl(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const window = requireBrowserWindow();
  const state = await collectPageState(window);
  await assertSamePublicOrigin(window, state.url);
  const control = resolveControl(state, { index: args.index });
  rejectPasswordControl(control.type);
  const text = sanitizeSingleLine(args.text ?? '', 500);
  if (!text) throw new Error(hostText('Yazılacak metin gerekli.', 'Text to type is required.'));
  const result = await runControlAction(window, {
    action: 'type',
    index: control.index,
    signature: controlSignature(control),
    text,
  });
  return { typed: true, index: control.index, url: result.url };
}

/** `browser_fill_form` — tek onay, tüm payload. */
export async function fillBrowserForm(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const window = requireBrowserWindow();
  const fields = Array.isArray(args.fields) ? args.fields : [];
  if (fields.length === 0) {
    throw new Error(hostText('Doldurulacak alan yok.', 'There are no fields to fill.'));
  }
  const filled: number[] = [];
  for (const field of fields) {
    if (!field || typeof field !== 'object') continue;
    const item = field as Record<string, unknown>;
    await typeBrowserControl({ index: item.index, text: item.text });
    filled.push(Number(item.index));
  }
  if (args.submit_index !== undefined && args.submit_index !== null) {
    await clickBrowserControl({ index: args.submit_index });
  }
  return {
    filled: true,
    fields: filled,
    submitted: args.submit_index !== undefined && args.submit_index !== null,
    url: window.webContents.getURL(),
  };
}

/** `browser_scroll` aracı. Pozitif değer aşağı, negatif değer yukarı kaydırır. */
export async function scrollBrowserPage(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const window = requireBrowserWindow();
  const amount = clamp(Number(args.amount ?? 700), -4000, 4000);
  if (amount === 0) throw new Error(hostText('Kaydırma miktarı sıfır olamaz.', 'Scroll amount cannot be zero.'));

  const position = (await window.webContents.executeJavaScript(
    `(() => {
      window.scrollBy({ top: ${Math.trunc(amount)}, behavior: 'smooth' });
      return { x: Math.round(window.scrollX), y: Math.round(window.scrollY) };
    })()`,
    true,
  )) as { x?: unknown; y?: unknown };
  await delay(600);

  return {
    scrolled: true,
    amount: Math.trunc(amount),
    position: { x: Number(position?.x ?? 0), y: Number(position?.y ?? 0) },
    url: window.webContents.getURL(),
  };
}

/** `browser_capture` aracı; yalnızca yönetilen web penceresini yakalar. */
export async function captureBrowserPage(): Promise<Record<string, unknown>> {
  const window = requireBrowserWindow();
  let image = await window.webContents.capturePage();
  for (let attempt = 0; image.isEmpty() && attempt < 3; attempt += 1) {
    window.show();
    window.webContents.invalidate();
    await delay(400);
    image = await window.webContents.capturePage();
  }
  if (image.isEmpty()) {
    throw new Error(hostText('Web sayfası görüntüsü alınamadı.', 'Could not capture the web page image.'));
  }

  const folder = await createOutputFolder();
  const filePath = path.join(folder, 'sayfa.png');
  await writeFile(filePath, image.toPNG());

  return {
    captured: true,
    path: filePath,
    title: window.webContents.getTitle(),
    source: window.webContents.getURL(),
    width: image.getSize().width,
    height: image.getSize().height,
  };
}

/** `browser_save_images` aracı; yalnızca açık sayfanın DOM'unda bulunan görselleri indirir. */
export async function saveBrowserImages(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const window = requireBrowserWindow();
  const limit = clamp(Number(args.max_results ?? 6), 1, MAX_MEDIA_RESULTS);
  const requiredText = sanitizeSingleLine(args.required_text ?? '', 160);
  const requiredTerms = normalizeSearchWords(requiredText);
  const state = await collectPageState(window);
  const candidates = state.images
    .filter((image) => !/static\.cdninstagram\.com\/rsrc\.php/i.test(image.url))
    .filter((image) => !/\b(connatix|video player|advertisement|logo|icon)\b/i.test(image.alt))
    .filter((image) => {
      if (!requiredTerms.length) return true;
      const words = new Set(normalizeSearchWords(image.alt));
      return requiredTerms.every((term) => words.has(term));
    })
    .slice(0, limit * 3);
  if (!candidates.length) {
    throw new Error(
      hostText(
        'Açık sayfada kaydedilebilir büyük bir görsel bulunamadı.',
        'No large savable image was found on the open page.',
      ),
    );
  }

  const folder = await createOutputFolder();
  const images: Array<Record<string, unknown>> = [];
  const failures: string[] = [];

  for (const candidate of candidates) {
    if (images.length >= limit) break;
    try {
      const downloaded = await downloadPageImage(window, candidate.url);
      const filePath = path.join(
        folder,
        `${String(images.length + 1).padStart(2, '0')}-${safeFileStem(candidate.alt)}.${downloaded.extension}`,
      );
      await writeFile(filePath, downloaded.data);
      images.push({
        path: filePath,
        title: candidate.alt || state.title || hostText('Web görseli', 'Web image'),
        source: state.url,
        original_url: candidate.url,
        width: candidate.width,
        height: candidate.height,
      });
    } catch (error) {
      failures.push(
        error instanceof Error ? error.message.slice(0, 160) : String(error).slice(0, 160),
      );
    }
  }

  if (!images.length) {
    const detail = failures.length
      ? hostText(
          ` Ayrıntı: ${[...new Set(failures)].slice(0, 3).join(' | ')}`,
          ` Detail: ${[...new Set(failures)].slice(0, 3).join(' | ')}`,
        )
      : '';
    throw new Error(
      hostText(
        `Sayfadaki görseller indirilemedi; site oturum veya erişim kısıtı uyguluyor.${detail}`,
        `The page images could not be downloaded; the site is applying a session or access restriction.${detail}`,
      ),
    );
  }
  return {
    saved: true,
    count: images.length,
    page_title: state.title,
    source: state.url,
    images,
  };
}

function normalizeSearchWords(value: string): string[] {
  return value
    .toLocaleLowerCase('tr-TR')
    .replace(/[çÇ]/g, 'c')
    .replace(/[ğĞ]/g, 'g')
    .replace(/[ıİ]/g, 'i')
    .replace(/[öÖ]/g, 'o')
    .replace(/[şŞ]/g, 's')
    .replace(/[üÜ]/g, 'u')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

function ensureBrowserWindow(): BrowserWindow {
  if (browserWindow && !browserWindow.isDestroyed()) return browserWindow;

  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 620,
    show: false,
    title: hostText('Uryx Web - Güvenli Oturum', 'Uryx Web - Secure Session'),
    backgroundColor: '#070b14',
    autoHideMenuBar: true,
    icon: resolveAppIconPath(),
    webPreferences: {
      partition: BROWSER_PARTITION,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      backgroundThrottling: false,
      spellcheck: false,
    },
  });

  const session = window.webContents.session;
  session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.setPermissionCheckHandler(() => false);
  session.on('will-download', (event) => event.preventDefault());
  session.webRequest.onBeforeRequest((details, callback) => {
    callback({ cancel: !isSafeBrowserResource(details.url) });
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    try {
      void window.loadURL(normalizePublicWebUrl(url));
    } catch {
    }
    return { action: 'deny' };
  });

  const guardNavigation = (event: Electron.Event, url: string): void => {
    try {
      normalizePublicWebUrl(url);
    } catch {
      event.preventDefault();
    }
  };
  window.webContents.on('will-navigate', guardNavigation);
  window.webContents.on('will-redirect', guardNavigation);

  window.on('closed', () => {
    if (browserWindow === window) browserWindow = null;
  });
  browserWindow = window;
  return window;
}

function requireBrowserWindow(): BrowserWindow {
  if (!browserWindow || browserWindow.isDestroyed()) {
    throw new Error(
      hostText(
        'Önce browser_open ile bir web sayfası açılmalı.',
        'A web page must be opened with browser_open first.',
      ),
    );
  }
  return browserWindow;
}

async function collectPageState(window: BrowserWindow): Promise<PageState> {
  const raw = (await window.webContents.executeJavaScript(
    `(() => {
      const clean = (value, limit) => String(value || '').replace(/\\s+/g, ' ').trim().slice(0, limit);
      const visible = (element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 1 && rect.height > 1 && style.display !== 'none' && style.visibility !== 'hidden';
      };
      const links = Array.from(document.querySelectorAll('a[href]'))
        .filter(visible)
        .map((element) => ({ text: clean(element.innerText || element.getAttribute('aria-label'), 180), url: element.href }))
        .filter((item) => /^https?:\\/\\//i.test(item.url))
        .slice(0, 60);
      const images = Array.from(document.querySelectorAll('img, video[poster]'))
        .filter(visible)
        .map((element) => {
          const isVideo = element instanceof HTMLVideoElement;
          const image = isVideo ? null : element;
          const rect = element.getBoundingClientRect();
          return {
            url: isVideo ? element.poster : (image.currentSrc || image.src),
            alt: clean(element.getAttribute('alt') || element.getAttribute('aria-label'), 160),
            width: isVideo ? Math.round(rect.width) : (image.naturalWidth || Math.round(rect.width)),
            height: isVideo ? Math.round(rect.height) : (image.naturalHeight || Math.round(rect.height)),
          };
        })
        .filter((item) => /^https?:\\/\\//i.test(item.url) && item.width >= 240 && item.height >= 160);
      const controlNodes = Array.from(document.querySelectorAll(
        'a[href], button, input, textarea, select, [role="button"], [role="textbox"], [role="link"], [contenteditable="true"]',
      )).filter(visible).slice(0, 80);
      const controls = controlNodes.map((element, index) => ({
        index,
        tag: String(element.tagName || '').toLowerCase(),
        type: clean(element.getAttribute('type'), 40).toLowerCase(),
        role: clean(element.getAttribute('role') || element.tagName, 40).toLowerCase(),
        name: clean(
          element.getAttribute('aria-label') ||
            element.getAttribute('placeholder') ||
            element.getAttribute('name') ||
            element.innerText,
          120,
        ),
        href: element instanceof HTMLAnchorElement ? element.href : null,
      }));
      return {
        title: clean(document.title, 300),
        url: location.href,
        text: String(document.body?.innerText || '').slice(0, ${MAX_PAGE_TEXT}),
        links,
        images,
        controls,
      };
    })()`,
    true,
  )) as Partial<PageState>;

  const seenImages = new Set<string>();
  const images = (Array.isArray(raw.images) ? raw.images : []).flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const candidate = item as Partial<PageImage>;
    const url = typeof candidate.url === 'string' ? candidate.url : '';
    if (!url.startsWith('http') || seenImages.has(url)) return [];
    seenImages.add(url);
    return [
      {
        url,
        alt: sanitizeSingleLine(candidate.alt ?? '', 160),
        width: Number(candidate.width ?? 0),
        height: Number(candidate.height ?? 0),
      },
    ];
  });

  return {
    title: sanitizeSingleLine(raw.title ?? window.webContents.getTitle(), 300),
    url: normalizePublicWebUrl(raw.url ?? window.webContents.getURL()),
    text: String(raw.text ?? '').slice(0, MAX_PAGE_TEXT),
    links: (Array.isArray(raw.links) ? raw.links : []).slice(0, 60).flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      const link = item as { text?: unknown; url?: unknown };
      try {
        return [
          {
            text: sanitizeSingleLine(link.text ?? '', 180),
            url: normalizePublicWebUrl(link.url),
          },
        ];
      } catch {
        return [];
      }
    }),
    images,
    controls: (Array.isArray(raw.controls) ? raw.controls : []).slice(0, 80).flatMap((item, index) => {
      if (!item || typeof item !== 'object') return [];
      const control = item as Partial<PageControl>;
      return [
        {
          index: Number.isInteger(control.index) ? Number(control.index) : index,
          tag: sanitizeSingleLine(control.tag ?? '', 40).toLowerCase(),
          type: sanitizeSingleLine(control.type ?? '', 40).toLowerCase(),
          role: sanitizeSingleLine(control.role ?? '', 40).toLowerCase(),
          name: sanitizeSingleLine(control.name ?? '', 120),
          href:
            typeof control.href === 'string' && control.href.startsWith('http') ? control.href : null,
        },
      ];
    }),
  };
}

export function isBrowserLoginWall(url: string, title: string, text = ''): boolean {
  const location = url.toLowerCase();
  const blob = `${title}\n${text.slice(0, 400)}`.toLowerCase();
  if (location.includes('/accounts/login') || location.includes('/accounts/emailsignup')) {
    return true;
  }
  return (
    location.includes('instagram.com') &&
    (blob.includes('log in') || blob.includes('giriş yap') || blob.includes('login • instagram'))
  );
}

function summarizeState(state: PageState, extra: Record<string, unknown>): Record<string, unknown> {
  return {
    ...extra,
    title: state.title,
    url: state.url,
    text: state.text,
    login_required: isBrowserLoginWall(state.url, state.title, state.text),
    links: state.links,
    image_count: state.images.length,
    images: state.images.slice(0, 10).map((image, index) => ({
      index: index + 1,
      alt: image.alt,
      width: image.width,
      height: image.height,
    })),
  };
}

async function downloadPageImage(
  window: BrowserWindow,
  url: string,
): Promise<{ data: Buffer; extension: string }> {
  const safeUrl = normalizePublicWebUrl(url);
  const response = await window.webContents.session.fetch(safeUrl, {
    credentials: 'include',
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) {
    throw new Error(
      hostText(`Görsel isteği başarısız: ${response.status}`, `Image request failed: ${response.status}`),
    );
  }

  const contentType = (response.headers.get('content-type') ?? '').split(';')[0]!.toLowerCase();
  const extension = imageExtension(contentType);
  if (!extension) {
    throw new Error(hostText('Yanıt desteklenen bir görsel değil.', 'The response is not a supported image.'));
  }
  const declaredLength = Number(response.headers.get('content-length') ?? 0);
  if (declaredLength > MAX_MEDIA_BYTES) {
    throw new Error(hostText('Görsel boyut sınırını aşıyor.', 'The image exceeds the size limit.'));
  }

  const data = Buffer.from(await response.arrayBuffer());
  if (!data.length || data.length > MAX_MEDIA_BYTES) {
    throw new Error(
      hostText('Görsel boş veya boyut sınırını aşıyor.', 'The image is empty or exceeds the size limit.'),
    );
  }
  return { data, extension };
}

async function createOutputFolder(): Promise<string> {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const folder = path.join(app.getPath('pictures'), 'Uryx', 'Web', stamp);
  await mkdir(folder, { recursive: true });
  return folder;
}

function imageExtension(contentType: string): string | null {
  const extensions: Record<string, string> = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
    'image/gif': 'gif',
    'image/bmp': 'bmp',
  };
  return extensions[contentType] ?? null;
}

function safeFileStem(value: string): string {
  const stem = value
    .normalize('NFKD')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 50);
  return stem || 'gorsel';
}

function isPrivateHostname(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (
    host === 'localhost' ||
    host.endsWith('.localhost') ||
    host.endsWith('.local') ||
    host.endsWith('.internal')
  ) {
    return true;
  }

  const version = isIP(host);
  if (version === 4) {
    const [a, b] = host.split('.').map(Number);
    return (
      a === 0 ||
      a === 10 ||
      a === 127 ||
      (a === 169 && b === 254) ||
      (a === 172 && b! >= 16 && b! <= 31) ||
      (a === 192 && b === 168) ||
      a! >= 224
    );
  }
  if (version === 6) {
    return host === '::1' || host === '::' || /^f[cd]/.test(host) || host.startsWith('fe8');
  }
  return !host.includes('.');
}

function isSafeBrowserResource(value: string): boolean {
  try {
    const parsed = new URL(value);
    if (['about:', 'blob:', 'data:', 'chrome-error:'].includes(parsed.protocol)) return true;
    if (['ws:', 'wss:'].includes(parsed.protocol)) {
      return !parsed.username && !parsed.password && !isPrivateHostname(parsed.hostname);
    }
    normalizePublicWebUrl(value);
    return true;
  } catch {
    return false;
  }
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.trunc(value)));
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error(message)), ms);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
