import { AudioQueue, concatPcmFrames, MicrophoneSession, MicRecorder } from '@/lib/audio';

interface FakeTrack {
  readyState: MediaStreamTrackState;
  stop: ReturnType<typeof vi.fn>;
  addEventListener: ReturnType<typeof vi.fn>;
}

function fakeStream(): { stream: MediaStream; track: FakeTrack } {
  const listeners = new Map<string, () => void>();
  const track: FakeTrack = {
    readyState: 'live',
    stop: vi.fn(() => {
      track.readyState = 'ended';
      listeners.get('ended')?.();
    }),
    addEventListener: vi.fn((name: string, listener: () => void) => {
      listeners.set(name, listener);
    }),
  };
  const stream = {
    getAudioTracks: () => [track],
    getTracks: () => [track],
  } as unknown as MediaStream;
  return { stream, track };
}

describe('MicrophoneSession', () => {
  it('reuses the same live stream for repeated recordings', async () => {
    const first = fakeStream();
    const getUserMedia = vi.fn().mockResolvedValue(first.stream);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });

    const session = new MicrophoneSession();
    await session.createRecorder({ deviceId: 'default' });
    await session.createRecorder({ deviceId: 'default' });

    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(first.track.stop).not.toHaveBeenCalled();
    session.close();
    expect(first.track.stop).toHaveBeenCalledOnce();
  });

  it('closes the old stream when the input device changes', async () => {
    const first = fakeStream();
    const second = fakeStream();
    const getUserMedia = vi
      .fn()
      .mockResolvedValueOnce(first.stream)
      .mockResolvedValueOnce(second.stream);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });

    const session = new MicrophoneSession();
    await session.open('microphone-a');
    await session.open('microphone-b');

    expect(first.track.stop).toHaveBeenCalledOnce();
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    session.close();
  });
});

describe('MicRecorder', () => {
  it('unblocks an auto-stop waiter when cancelled', async () => {
    const recorder = new MicRecorder();
    const stopped = recorder.waitForAutoStop();

    recorder.cancel();

    await expect(stopped).resolves.toBeUndefined();
  });
});

describe('concatPcmFrames', () => {
  it('kareleri birleştirir ve tavanı keser', () => {
    expect(Array.from(concatPcmFrames([new Float32Array([1, 2]), new Float32Array([3])]))).toEqual([
      1, 2, 3,
    ]);
    const long = concatPcmFrames([new Float32Array([1, 2, 3, 4])], 2);
    expect(Array.from(long)).toEqual([3, 4]);
  });
});

describe('AudioQueue', () => {
  it('decodes early and plays buffers in order', async () => {
    const played: number[] = [];
    let decoded = 0;

    class FakeSource {
      buffer: AudioBuffer | null = null;
      onended: (() => void) | null = null;

      connect(): void {}
      start(): void {
        played.push((this.buffer as unknown as { id: number }).id);
        window.setTimeout(() => this.onended?.(), 0);
      }
      stop(): void {
        this.onended?.();
      }
    }

    const fakeContext = {
      state: 'running',
      destination: {},
      decodeAudioData: vi.fn(async () => ({ id: (decoded += 1) }) as unknown as AudioBuffer),
      createBufferSource: vi.fn(() => new FakeSource()),
      createGain: vi.fn(() => ({
        gain: { value: 1 },
        connect: vi.fn(),
      })),
      resume: vi.fn(),
    };
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: vi.fn(() => fakeContext),
    });

    const states: boolean[] = [];
    const queue = new AudioQueue();
    queue.onStateChange = (playing) => states.push(playing);
    queue.enqueueBase64(window.btoa('first'));
    queue.enqueueBase64(window.btoa('second'));
    await new Promise((resolve) => window.setTimeout(resolve, 20));

    expect(fakeContext.decodeAudioData).toHaveBeenCalledTimes(2);
    expect(played).toEqual([1, 2]);
    expect(states.at(-1)).toBe(false);
  });

  it('stop playback offset ile söylenen metni döner', async () => {
    class FakeSource {
      buffer: AudioBuffer | null = null;
      onended: (() => void) | null = null;
      connect(): void {}
      start(): void {}
      stop(): void {
        this.onended?.();
      }
    }

    const fakeContext = {
      state: 'running',
      destination: {},
      currentTime: 0,
      decodeAudioData: vi.fn(async () => ({ duration: 2 }) as unknown as AudioBuffer),
      createBufferSource: vi.fn(() => new FakeSource()),
      createGain: vi.fn(() => ({
        gain: { value: 1 },
        connect: vi.fn(),
      })),
      resume: vi.fn(),
    };
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: vi.fn(() => fakeContext),
    });

    const queue = new AudioQueue();
    queue.enqueueBase64(window.btoa('clip'), 'audio/wav', 'Merhaba dünya.', true);
    await new Promise((resolve) => window.setTimeout(resolve, 10));
    fakeContext.currentTime = 1;
    const spoken = queue.stop();
    expect(spoken).toBe('Merhaba');
  });
});
