/**
 * Mikrofon kaydı ve ses oynatma.
 *
 * - `MicRecorder`: MediaRecorder ile kayıt, enerji+ZCR VAD
 *   (sessizlik algılayınca otomatik durdurma).
 * - `AudioQueue`: TTS'ten gelen WAV parçalarını sırayla, kesintisiz oynatır.
 */

import { spokenFromPlayback } from '@/lib/bargeIn';
import { tNow } from '@/lib/tNow';
import { createEnergyZcrVad } from '@/lib/vad';

export interface MicRecorderOptions {
  deviceId?: string;
  /** Reuse an already-open microphone stream without taking ownership of its tracks. */
  stream?: MediaStream;
  /** Sessizlik eşiği (0-1 RMS). */
  noiseThreshold?: number;
  /** Bu süre kadar sessizlik olursa kayıt otomatik biter (ms). */
  silenceTimeoutMs?: number;
  /** Konuşma hiç başlamazsa bu sürenin sonunda kayıt otomatik biter (ms). */
  initialSilenceTimeoutMs?: number;
  /** Raise the speech threshold automatically when ambient noise increases. */
  adaptiveNoiseFloor?: boolean;
  /** Ses seviyesi değiştikçe çağrılır (0-1). */
  onLevel?: (level: number) => void;
  /** Gürültü eşiği ilk kez aşıldığında çağrılır. */
  onSpeechStart?: () => void;
  /** VAD kaydı otomatik durdurduğunda çağrılır. */
  onAutoStop?: () => void;
  /** MediaRecorder dilimi (Whisper akışı). */
  onChunk?: (chunk: Blob) => void;
  /** Analyser PCM'ini biriktir (wake host'a IPC). */
  capturePcm?: boolean;
}

/** PCM karelerini birleştirir; `maxSamples` dolunca başı atar. */
export function concatPcmFrames(frames: Float32Array[], maxSamples = Number.POSITIVE_INFINITY): Float32Array {
  const total = frames.reduce((sum, frame) => sum + frame.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const frame of frames) {
    out.set(frame, offset);
    offset += frame.length;
  }
  if (out.length <= maxSamples) return out;
  return out.subarray(out.length - maxSamples);
}

/** Mikrofon kaydedicisi. */
export class MicRecorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private rafId: number | null = null;
  private speechDetected = false;
  private ownsStream = false;
  private autoStopPromise: Promise<void> | null = null;
  private resolveAutoStop: (() => void) | null = null;
  private pcmFrames: Float32Array[] = [];
  private pcmSampleRate = 48_000;

  constructor(private readonly options: MicRecorderOptions = {}) {}

  /** Kayıt sürüyor mu? */
  get isRecording(): boolean {
    return this.recorder?.state === 'recording';
  }

  /** Bu kayıtta gürültü eşiğini aşan bir ses algılandı mı? */
  get hadSpeech(): boolean {
    return this.speechDetected;
  }

  /** Wake host için birikmiş PCM (son ~2 s). */
  takePcm(): { samples: Float32Array; sampleRate: number } | null {
    if (!this.options.capturePcm || this.pcmFrames.length === 0) return null;
    const maxSamples = Math.floor(this.pcmSampleRate * 2);
    const samples = concatPcmFrames(this.pcmFrames, maxSamples);
    return samples.length ? { samples: new Float32Array(samples), sampleRate: this.pcmSampleRate } : null;
  }

  /** Resolves when VAD ends the utterance or the recorder is cancelled. */
  waitForAutoStop(): Promise<void> {
    if (!this.autoStopPromise) {
      this.autoStopPromise = new Promise<void>((resolve) => {
        this.resolveAutoStop = resolve;
      });
    }
    return this.autoStopPromise;
  }

  /**
   * Kaydı başlatır.
   * @throws Mikrofon izni yoksa veya cihaz bulunamazsa.
   */
  async start(): Promise<void> {
    if (this.isRecording) return;

    if (this.options.stream) {
      this.stream = this.options.stream;
      this.ownsStream = false;
    } else {
      this.ownsStream = true;
      const constraints: MediaStreamConstraints = {
        audio: {
          deviceId:
            this.options.deviceId && this.options.deviceId !== 'default'
              ? { exact: this.options.deviceId }
              : undefined,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      };

      try {
        this.stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (error) {
        const name = (error as DOMException)?.name;
        if (name === 'NotAllowedError') {
          throw new Error(tNow('audio.denied'));
        }
        if (name === 'NotFoundError') {
          throw new Error(tNow('audio.notFound'));
        }
        throw new Error(tNow('audio.openFail', { error: String(error) }));
      }
    }

    this.chunks = [];
    this.pcmFrames = [];
    this.speechDetected = false;

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : '';

    this.recorder = new MediaRecorder(this.stream, mimeType ? { mimeType } : undefined);
    this.recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        this.chunks.push(event.data);
        this.options.onChunk?.(event.data);
      }
    };
    this.recorder.start(250);

    this.startLevelMonitor();
  }

  /** Ses seviyesi izleyicisini başlatır (enerji + sıfır geçişi VAD). */
  private startLevelMonitor(): void {
    if (!this.stream) return;

    const AudioContextCtor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.audioContext = new AudioContextCtor();
    this.pcmSampleRate = this.audioContext.sampleRate || 48_000;
    const source = this.audioContext.createMediaStreamSource(this.stream);
    this.analyser = this.audioContext.createAnalyser();
    this.analyser.fftSize = 1024;
    source.connect(this.analyser);

    const buffer = new Float32Array(this.analyser.fftSize);
    const vad = createEnergyZcrVad({
      noiseThreshold: this.options.noiseThreshold,
      adaptiveNoiseFloor: this.options.adaptiveNoiseFloor,
      silenceTimeoutMs: this.options.silenceTimeoutMs,
      initialSilenceTimeoutMs: this.options.initialSilenceTimeoutMs,
      onLevel: this.options.onLevel,
      onSpeechStart: () => {
        this.speechDetected = true;
        this.options.onSpeechStart?.();
      },
      onAutoStop: () => this.signalAutoStop(),
    });

    const tick = (): void => {
      if (!this.analyser) return;
      this.analyser.getFloatTimeDomainData(buffer);
      if (this.options.capturePcm) {
        this.pcmFrames.push(Float32Array.from(buffer));
      }
      const decision = vad.push(buffer);
      this.speechDetected = vad.speechDetected;
      if (decision === 'auto-stop') return;
      this.rafId = requestAnimationFrame(tick);
    };

    this.rafId = requestAnimationFrame(tick);
  }

  /**
   * Kaydı durdurur ve ses verisini döndürür.
   * @returns Kayıt boşsa `null`.
   */
  async stop(): Promise<Blob | null> {
    const recorder = this.recorder;
    if (!recorder || recorder.state === 'inactive') {
      this.cleanup();
      return null;
    }

    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => {
        resolve(new Blob(this.chunks, { type: recorder.mimeType || 'audio/webm' }));
      };
      recorder.stop();
    });

    this.cleanup();
    return blob.size > 1000 ? blob : null;
  }

  /** Kaydı iptal eder. */
  cancel(): void {
    if (this.recorder?.state === 'recording') this.recorder.stop();
    this.chunks = [];
    this.resolveAutoStop?.();
    this.cleanup();
  }

  private signalAutoStop(): void {
    this.options.onAutoStop?.();
    this.resolveAutoStop?.();
  }

  private cleanup(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.analyser = null;
    this.pcmFrames = [];
    void this.audioContext?.close().catch(() => undefined);
    this.audioContext = null;
    if (this.ownsStream) this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.ownsStream = false;
    this.recorder = null;
    this.resolveAutoStop = null;
    this.options.onLevel?.(0);
  }
}

/** Kullanılabilir mikrofon cihazlarını listeler. */
/** Keeps one microphone stream alive across wake and conversation recordings. */
export class MicrophoneSession {
  private stream: MediaStream | null = null;
  private deviceId = 'default';
  private opening: Promise<MediaStream> | null = null;

  async createRecorder(options: MicRecorderOptions = {}): Promise<MicRecorder> {
    const stream = await this.open(options.deviceId);
    return new MicRecorder({ ...options, stream });
  }

  async open(deviceId = 'default'): Promise<MediaStream> {
    const requestedDevice = deviceId || 'default';
    if (this.deviceId !== requestedDevice) this.close();
    if (this.stream && this.stream.getAudioTracks().some((track) => track.readyState === 'live')) {
      return this.stream;
    }
    if (this.opening) return this.opening;

    this.deviceId = requestedDevice;
    this.opening = navigator.mediaDevices
      .getUserMedia({
        audio: {
          deviceId: requestedDevice !== 'default' ? { exact: requestedDevice } : undefined,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      .then((stream) => {
        this.stream = stream;
        for (const track of stream.getAudioTracks()) {
          track.addEventListener('ended', () => {
            if (this.stream === stream) this.stream = null;
          });
        }
        return stream;
      })
      .finally(() => {
        this.opening = null;
      });

    return this.opening;
  }

  close(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.opening = null;
  }
}

export async function listMicrophones(): Promise<{ deviceId: string; label: string }[]> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
  } catch {
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((device) => device.kind === 'audioinput')
    .map((device, index) => ({
      deviceId: device.deviceId || 'default',
      label: device.label || tNow('audio.micN', { n: index + 1 }),
    }));
}

/**
 * TTS ses parçalarını sırayla oynatan kuyruk.
 *
 * Backend cümle bazında ses ürettiği için parçalar geldikçe eklenir ve
 * kesintisiz çalınır.
 */
export class AudioQueue {
  private queue: Array<{ generation: number; audio: Promise<AudioBuffer | null>; text: string }> = [];
  private context: AudioContext | null = null;
  private current: AudioBufferSourceNode | null = null;
  private currentGain: GainNode | null = null;
  private playing = false;
  private volume = 1;
  private generation = 0;
  private spokenCompleted: string[] = [];
  private currentText = '';
  private playbackStartedAt = 0;
  private playbackDuration = 0;
  private lastSpoken = '';
  private live = false;

  /** Oynatma durumu değişince tetiklenir. */
  onStateChange?: (playing: boolean) => void;

  get isPlaying(): boolean {
    return this.playing;
  }

  /** Ses seviyesini ayarlar (0-2). */
  setVolume(volume: number): void {
    this.volume = Math.max(0, Math.min(volume, 2));
    if (this.currentGain) this.currentGain.gain.value = this.volume;
  }

  /** Base64 WAV parçasını kuyruğa ekler. */
  enqueueBase64(base64: string, _mimeType = 'audio/wav', text = '', live = false): void {
    const binary = window.atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    if (live) this.live = true;
    this.enqueueDecode(bytes.buffer, text);
  }

  /** Blob'u kuyruğa ekler. */
  enqueueBlob(blob: Blob): void {
    const generation = this.generation;
    const audio = blob.arrayBuffer().then((buffer) => this.decode(buffer));
    this.queue.push({ generation, audio, text: '' });
    void this.playQueued();
  }

  private enqueueDecode(buffer: ArrayBuffer, text = ''): void {
    const generation = this.generation;
    this.queue.push({ generation, audio: this.decode(buffer), text });
    void this.playQueued();
  }

  private audioContext(): AudioContext {
    if (this.context) return this.context;
    const AudioContextCtor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.context = new AudioContextCtor();
    return this.context;
  }

  private async decode(buffer: ArrayBuffer): Promise<AudioBuffer | null> {
    try {
      return await this.audioContext().decodeAudioData(buffer.slice(0));
    } catch {
      return null;
    }
  }

  private async playQueued(): Promise<void> {
    if (this.playing) return;
    this.playing = true;
    const runGeneration = this.generation;

    try {
      while (this.queue.length > 0 && runGeneration === this.generation) {
        const next = this.queue.shift();
        if (!next || next.generation !== runGeneration) continue;
        this.currentText = next.text;
        const buffer = await next.audio;
        if (!buffer || runGeneration !== this.generation) continue;
        await this.playBuffer(buffer, runGeneration);
        if (runGeneration === this.generation && next.text) {
          this.spokenCompleted.push(next.text);
          this.currentText = '';
        }
      }
    } finally {
      if (runGeneration === this.generation) {
        this.playing = false;
        this.onStateChange?.(false);
      }
    }
  }

  private async playBuffer(buffer: AudioBuffer, runGeneration: number): Promise<void> {
    const context = this.audioContext();
    if (context.state === 'suspended') await context.resume();

    const source = context.createBufferSource();
    const gain = context.createGain();
    source.buffer = buffer;
    gain.gain.value = this.volume;
    source.connect(gain);
    gain.connect(context.destination);
    this.current = source;
    this.currentGain = gain;
    this.playbackStartedAt = context.currentTime;
    this.playbackDuration = buffer.duration || 0;
    this.onStateChange?.(true);

    await new Promise<void>((resolve) => {
      source.onended = () => resolve();
      source.start();
    });

    if (runGeneration === this.generation) {
      this.current = null;
      this.currentGain = null;
    }
  }

  /** Kuyruğu temizler ve oynatmayı durdurur; söylenen metni döner. */
  stop(): string {
    const now = this.context?.currentTime ?? this.playbackStartedAt;
    const fraction =
      this.playbackDuration > 0 ? (now - this.playbackStartedAt) / this.playbackDuration : 0;
    const heard = this.live
      ? spokenFromPlayback(this.spokenCompleted, this.currentText, fraction)
      : '';
    const spoken = heard || this.lastSpoken;
    this.lastSpoken = spoken;
    this.generation += 1;
    this.queue = [];
    this.spokenCompleted = [];
    this.currentText = '';
    this.playbackDuration = 0;
    this.live = false;
    if (this.current) {
      try {
        this.current.stop();
      } catch {
      }
      this.current = null;
    }
    this.currentGain = null;
    this.playing = false;
    this.onStateChange?.(false);
    return spoken;
  }
}

interface NativeSpeechItem {
  generation: number;
  text: string;
  voiceName: string;
  rate: number;
  live: boolean;
}

/** Windows'un kurulu OneCore seslerini kullanan sıralı, çevrimdışı TTS kuyruğu. */
export class NativeSpeechQueue {
  private queue: NativeSpeechItem[] = [];
  private generation = 0;
  private playing = false;
  private volume = 1;
  private spokenCompleted: string[] = [];
  private currentText = '';
  private currentCharIndex = 0;
  private lastSpoken = '';
  private live = false;

  onStateChange?: (playing: boolean) => void;

  get isPlaying(): boolean {
    return this.playing;
  }

  setVolume(volume: number): void {
    this.volume = Math.max(0, Math.min(volume, 1));
  }

  enqueue(text: string, voiceName: string, rate = 1, live = false): void {
    const clean = text.trim();
    if (!clean) return;
    if (live) this.live = true;
    this.queue.push({
      generation: this.generation,
      text: clean,
      voiceName,
      rate: Math.max(0.5, Math.min(rate, 2)),
      live,
    });
    void this.playQueued();
  }

  private async playQueued(): Promise<void> {
    if (this.playing) return;
    this.playing = true;
    const runGeneration = this.generation;
    try {
      while (this.queue.length > 0 && runGeneration === this.generation) {
        const next = this.queue.shift();
        if (!next || next.generation !== runGeneration) continue;
        this.currentText = next.text;
        this.currentCharIndex = 0;
        await this.speak(next, runGeneration);
        if (runGeneration === this.generation && next.text) {
          this.spokenCompleted.push(next.text);
          this.currentText = '';
        }
      }
    } finally {
      if (runGeneration === this.generation) {
        this.playing = false;
        this.onStateChange?.(false);
      }
    }
  }

  private async speak(item: NativeSpeechItem, runGeneration: number): Promise<void> {
    const voices = await this.loadVoices();
    if (runGeneration !== this.generation) return;
    const wanted = item.voiceName.toLocaleLowerCase('tr-TR');
    const voice =
      voices.find((candidate) => candidate.name.toLocaleLowerCase('tr-TR') === wanted) ??
      voices.find((candidate) =>
        /natural|online/.test(candidate.name.toLocaleLowerCase('tr-TR')) &&
        candidate.lang.toLocaleLowerCase('tr-TR').startsWith('tr'),
      ) ??
      voices.find((candidate) =>
        /ahmet|emel/.test(candidate.name.toLocaleLowerCase('tr-TR')),
      ) ??
      voices.find((candidate) => candidate.lang.toLocaleLowerCase('tr-TR').startsWith('tr')) ??
      voices.find((candidate) =>
        candidate.name.toLocaleLowerCase('tr-TR').includes('microsoft tolga'),
      );

    const utterance = new SpeechSynthesisUtterance(item.text);
    utterance.lang = 'tr-TR';
    utterance.rate = item.rate;
    utterance.volume = this.volume;
    if (voice) utterance.voice = voice;
    utterance.onboundary = (event) => {
      this.currentCharIndex = event.charIndex;
    };
    this.onStateChange?.(true);
    await new Promise<void>((resolve) => {
      utterance.onend = () => resolve();
      utterance.onerror = () => resolve();
      window.speechSynthesis.speak(utterance);
    });
  }

  private async loadVoices(): Promise<SpeechSynthesisVoice[]> {
    const existing = window.speechSynthesis.getVoices();
    if (existing.length) return existing;
    return new Promise((resolve) => {
      const finish = (): void => {
        window.speechSynthesis.removeEventListener('voiceschanged', finish);
        resolve(window.speechSynthesis.getVoices());
      };
      window.speechSynthesis.addEventListener('voiceschanged', finish, { once: true });
      window.setTimeout(finish, 1000);
    });
  }

  stop(): string {
    const fraction =
      this.currentText.length > 0 ? this.currentCharIndex / this.currentText.length : 0;
    const heard = this.live
      ? spokenFromPlayback(this.spokenCompleted, this.currentText, fraction)
      : '';
    const spoken = heard || this.lastSpoken;
    this.lastSpoken = spoken;
    this.generation += 1;
    this.queue = [];
    this.spokenCompleted = [];
    this.currentText = '';
    this.currentCharIndex = 0;
    this.live = false;
    window.speechSynthesis.cancel();
    this.playing = false;
    this.onStateChange?.(false);
    return spoken;
  }
}
