import { afterEach, describe, expect, it } from 'vitest';

import {
  STT_HOTWORDS,
  SttStream,
  formatSttHudCaption,
  parseSttStreamEvent,
  speechTranscribeWsUrl,
  sttStreamControl,
} from '@/lib/sttStream';

/**
 * agentos DeepgramStreamingSTT.test — MockWebSocket nextTick open / reject-400 asla asılı kalmaz.
 * Deepgram Results / is_final çalınmadı; bizim partial/final.
 */
class FakeSpeechSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static nextBehavior: 'open' | 'error' = 'open';

  readyState = 0;
  binaryType = 'blob';
  sent: unknown[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(public url: string) {
    queueMicrotask(() => {
      if (FakeSpeechSocket.nextBehavior === 'error') {
        this.readyState = FakeSpeechSocket.CLOSED;
        this.onerror?.(new Event('error'));
        this.onclose?.(new CloseEvent('close'));
        return;
      }
      this.readyState = FakeSpeechSocket.OPEN;
      this.onopen?.(new Event('open'));
    });
  }

  send(data: unknown): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = FakeSpeechSocket.CLOSED;
    this.onclose?.(new CloseEvent('close'));
  }

  emitMessage(data: string): void {
    this.onmessage?.({ data } as MessageEvent);
  }
}

describe('sttStream', () => {
  it('API vekil adresini üretir', () => {
    expect(speechTranscribeWsUrl('http://127.0.0.1:8080', 'tok')).toBe(
      'ws://127.0.0.1:8080/ws/speech/transcribe?token=tok',
    );
  });

  it('start/end hotwords taşır, prefix yok', () => {
    const start = JSON.parse(sttStreamControl('start')) as {
      type: string;
      hotwords: string;
      prefix?: string;
    };
    expect(start.type).toBe('start');
    expect(start.hotwords).toBe(STT_HOTWORDS);
    expect(start.prefix).toBeUndefined();
    expect(JSON.parse(sttStreamControl('end', 'tr')).type).toBe('end');
  });

  it('partial/final çerçeveyi okur', () => {
    expect(parseSttStreamEvent({ type: 'partial', text: ' merhaba ' })).toEqual({
      kind: 'partial',
      text: 'merhaba',
    });
    expect(parseSttStreamEvent({ type: 'final', text: 'tamam' }).kind).toBe('final');
  });

  it('HUD aperçu taslağı kısaltır, boşta gizler', () => {
    expect(formatSttHudCaption('  merhaba   dünya  ')).toBe('merhaba dünya');
    expect(formatSttHudCaption('')).toBe('');
    expect(formatSttHudCaption('x'.repeat(120)).endsWith('…')).toBe(true);
    expect(formatSttHudCaption('x'.repeat(120)).length).toBe(96);
  });

  afterEach(() => {
    FakeSpeechSocket.nextBehavior = 'open';
  });

  it('WS mock: open start gönderir, partial HUD, final end çözer', async () => {
    let socket: FakeSpeechSocket | undefined;
    const stream = new SttStream((url) => {
      socket = new FakeSpeechSocket(url);
      return socket as unknown as WebSocket;
    });
    const partials: string[] = [];
    await expect(stream.connect((text) => partials.push(text))).resolves.toBe(true);
    expect(socket).toBeDefined();
    expect(JSON.parse(String(socket?.sent[0]))).toMatchObject({
      type: 'start',
      hotwords: STT_HOTWORDS,
    });

    socket?.emitMessage(JSON.stringify({ type: 'partial', text: ' mer ' }));
    expect(partials).toEqual(['mer']);

    const ended = stream.end('tr');
    expect(JSON.parse(String(socket?.sent[1]))).toMatchObject({ type: 'end', language: 'tr' });
    socket?.emitMessage(JSON.stringify({ type: 'final', text: 'merhaba' }));
    await expect(ended).resolves.toBe('merhaba');
  });

  it('WS mock: upgrade reddi asılı kalmaz', async () => {
    FakeSpeechSocket.nextBehavior = 'error';
    const stream = new SttStream((url) => new FakeSpeechSocket(url) as unknown as WebSocket);
    await expect(stream.connect()).resolves.toBe(false);
  });
});
