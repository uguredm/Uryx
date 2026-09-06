/**
 * Uryx paylaşılan tipleri.
 *
 * Bu paket, Electron (main + renderer) ile FastAPI backend arasındaki
 * REST/WebSocket sözleşmesinin TypeScript karşılığıdır. Python tarafı
 * `apps/api/app/schemas` içindedir ve elle senkron tutulur.
 */

export * from './api';
export * from './ws';
export * from './ipc';
export * from './settings';
