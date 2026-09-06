/** `electron-store` yerine bellek içi basit bir depo. */

interface StoreOptions<T> {
  name?: string;
  defaults?: T;
  clearInvalidConfig?: boolean;
}

export default class Store<T extends Record<string, unknown>> {
  private data: Record<string, unknown>;
  readonly path = '/tmp/uryx-test/settings.json';

  constructor(options: StoreOptions<T> = {}) {
    this.data = { ...(options.defaults ?? {}) };
  }

  get<K extends keyof T>(key: K): T[K] {
    return this.data[key as string] as T[K];
  }

  set<K extends keyof T>(key: K, value: T[K]): void {
    this.data[key as string] = value;
  }

  clear(): void {
    this.data = {};
  }
}
