/** Pencere / tepsi için uygulama ikonu yolu. */

import { app } from 'electron';
import { existsSync } from 'node:fs';
import path from 'node:path';

/** İlk bulunan .ico veya .png; yoksa undefined (Windows exe ikonuna düşer). */
export function resolveAppIconPath(): string | undefined {
  const resources = process.resourcesPath ?? '';
  const candidates = [
    path.join(__dirname, '../../build/icon.ico'),
    path.join(__dirname, '../../build/icon.png'),
    path.join(resources, 'icon.ico'),
    path.join(resources, 'icon.png'),
    path.join(app.getAppPath(), 'build', 'icon.ico'),
    path.join(app.getAppPath(), 'build', 'icon.png'),
  ];
  return candidates.find((candidate) => candidate.length > 0 && existsSync(candidate));
}
