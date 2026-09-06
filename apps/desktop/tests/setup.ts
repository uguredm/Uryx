/** Vitest genel kurulumu. */

import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach } from 'vitest';

import { setHostLanguage } from '../electron/host-i18n';

process.env.URYX_TEST_ROOT ??= mkdtempSync(join(tmpdir(), 'uryx-test-'));

beforeEach(() => {
  setHostLanguage('tr');
});

afterEach(() => {
  setHostLanguage('en');
});
