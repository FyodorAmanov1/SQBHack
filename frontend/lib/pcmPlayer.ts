/**
 * Plays mono 16-bit PCM chunks at a fixed sample rate (e.g. 24 kHz TTS output).
 */
export type PcmPlayerOptions = {
  /** Prefer scheduling stability over minimum latency (separate from capture). */
  latencyHint?: AudioContextLatencyCategory;
};

export class PcmPlayer {
  private ctx: AudioContext | null = null;
  private nextTime = 0;
  private readonly sampleRate: number;
  private readonly latencyHint: AudioContextLatencyCategory;

  constructor(sampleRate: number, opts?: PcmPlayerOptions) {
    this.sampleRate = sampleRate;
    this.latencyHint = opts?.latencyHint ?? "playback";
  }

  async ensureRunning(): Promise<void> {
    if (!this.ctx) {
      this.ctx = new AudioContext({
        sampleRate: this.sampleRate,
        latencyHint: this.latencyHint,
      });
      this.nextTime = 0;
    }
    if (this.ctx.state === "suspended") {
      await this.ctx.resume();
    }
  }

  enqueue(pcm: ArrayBuffer): void {
    if (!this.ctx) return;
    const i16 = new Int16Array(pcm);
    if (i16.length === 0) return;
    const buf = this.ctx.createBuffer(1, i16.length, this.sampleRate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < i16.length; i++) {
      ch[i] = i16[i] / 32768;
    }
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);
    const t = Math.max(this.ctx.currentTime, this.nextTime);
    src.start(t);
    this.nextTime = t + buf.duration;
  }

  reset(): void {
    if (this.ctx) {
      this.nextTime = this.ctx.currentTime;
    }
  }

  close(): void {
    if (this.ctx) {
      void this.ctx.close();
      this.ctx = null;
      this.nextTime = 0;
    }
  }
}
