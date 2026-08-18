const midiToFreq = (midi: number) => 440 * Math.pow(2, (midi - 69) / 12);

const CHORD_DURATION = 10;
const CHORDS = [
  { root: 45, tones: [57, 60, 64] },
  { root: 41, tones: [53, 57, 60] },
  { root: 48, tones: [52, 55, 60] },
  { root: 43, tones: [55, 59, 62] }
];
const PLUCK_STEP = 0.62;
const PLUCK_SCALE = [69, 72, 74, 76, 79, 81];
const PLUCK_PATTERN = [0, -1, 2, -1, 3, -1, 1, -1, 0, 2, -1, 3, 4, -1, 2, -1];
export const JINGLE_NOTES = [67, 72, 76, 79];
const JINGLE_STEP = 0.26;
export const MUSIC_TAIL = 6;
/** Breath between spoken scenes so cuts never clip the last word. */
const SCENE_BREATH = 0.45;

interface Voice {
  src: AudioScheduledSourceNode;
  gain: GainNode;
}

export class NovaAudioEngine {
  private readonly ctx: AudioContext;
  private readonly master: GainNode;
  private readonly narrationBus: GainNode;
  private readonly musicBus: GainNode;
  private readonly padFilter: BiquadFilterNode;
  private readonly reverb: ConvolverNode;
  private readonly reverbGain: GainNode;

  private buffers: AudioBuffer[] = [];
  private starts: number[] = [];
  private total = 0;
  private finaleTime = 0;

  private narrationSources: AudioBufferSourceNode[] = [];
  private musicVoices: Voice[] = [];
  private musicTimer: number | null = null;
  private nextEventTime = 0;
  private lastChordIndex = -1;
  private lastPluckIndex = -1;
  private openingJingleDone = false;
  private finaleJingleDone = false;
  private startOffset = 0;

  constructor(ctx: AudioContext) {
    this.ctx = ctx;
    this.master = ctx.createGain();
    this.master.gain.value = 1;
    this.master.connect(ctx.destination);

    this.narrationBus = ctx.createGain();
    this.narrationBus.gain.value = 0.96;
    this.narrationBus.connect(this.master);

    this.musicBus = ctx.createGain();
    this.musicBus.gain.value = 0.13;
    this.musicBus.connect(this.master);

    this.padFilter = ctx.createBiquadFilter();
    this.padFilter.type = "lowpass";
    this.padFilter.frequency.value = 980;
    this.padFilter.Q.value = 0.45;
    this.padFilter.connect(this.musicBus);

    this.reverb = ctx.createConvolver();
    this.reverb.buffer = NovaAudioEngine.makeImpulseResponse(ctx, 2.6, 2.5);
    this.reverbGain = ctx.createGain();
    this.reverbGain.gain.value = 0.5;
    this.reverb.connect(this.reverbGain);
    this.reverbGain.connect(this.musicBus);

    const lfo = ctx.createOscillator();
    const lfoGain = ctx.createGain();
    lfo.frequency.value = 0.06;
    lfoGain.gain.value = 180;
    lfo.connect(lfoGain);
    lfoGain.connect(this.padFilter.frequency);
    lfo.start();
  }

  private static makeImpulseResponse(ctx: AudioContext, seconds: number, decay: number): AudioBuffer {
    const rate = ctx.sampleRate;
    const length = Math.floor(rate * seconds);
    const buffer = ctx.createBuffer(2, length, rate);
    for (let channel = 0; channel < 2; channel += 1) {
      const data = buffer.getChannelData(channel);
      for (let i = 0; i < length; i += 1) {
        data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, decay);
      }
    }
    return buffer;
  }

  async load(files: string[]): Promise<void> {
    const decoded = await Promise.all(
      files.map(async (file) => {
        const response = await fetch(file);
        if (!response.ok) throw new Error(`Narration load failed: ${file}`);
        const arrayBuffer = await response.arrayBuffer();
        return this.ctx.decodeAudioData(arrayBuffer);
      })
    );
    this.buffers = decoded;
    const starts: number[] = [];
    let acc = 0;
    for (const buffer of decoded) {
      starts.push(acc);
      acc += buffer.duration + SCENE_BREATH;
    }
    this.starts = starts;
    this.total = acc - SCENE_BREATH + MUSIC_TAIL;
    this.finaleTime = starts[starts.length - 1] ?? 0;
  }

  get duration(): number {
    return this.total;
  }

  get sceneStarts(): number[] {
    return this.starts;
  }

  currentTime(): number {
    return Math.max(0, Math.min(this.total, this.ctx.currentTime - this.startOffset));
  }

  play(from: number): void {
    this.seekInternal(from);
    if (this.ctx.state === "suspended") void this.ctx.resume();
    this.startMusicScheduler();
  }

  resume(): void {
    if (this.ctx.state === "suspended") void this.ctx.resume();
    this.startMusicScheduler();
  }

  pause(): void {
    if (this.ctx.state === "running") void this.ctx.suspend();
  }

  seek(seconds: number): void {
    this.seekInternal(Math.max(0, Math.min(this.total - 0.05, seconds)));
  }

  setMuted(muted: boolean): void {
    const now = this.ctx.currentTime;
    this.master.gain.cancelScheduledValues(now);
    this.master.gain.setValueAtTime(this.master.gain.value, now);
    this.master.gain.linearRampToValueAtTime(muted ? 0 : 1, now + 0.08);
  }

  private seekInternal(target: number): void {
    this.stopNarration();
    this.stopMusic();
    this.startOffset = this.ctx.currentTime - target;

    const now = this.ctx.currentTime;
    for (let i = 0; i < this.buffers.length; i += 1) {
      const segmentStart = this.starts[i];
      const segmentEnd = segmentStart + this.buffers[i].duration;
      if (segmentEnd <= target) continue;
      const offset = Math.max(0, target - segmentStart);
      const source = this.ctx.createBufferSource();
      source.buffer = this.buffers[i];
      source.connect(this.narrationBus);
      source.start(now + Math.max(0, segmentStart - target), offset);
      this.narrationSources.push(source);
    }

    this.nextEventTime = target;
    this.lastChordIndex = Math.floor(target / CHORD_DURATION);
    this.lastPluckIndex = Math.floor(target / PLUCK_STEP);
    this.openingJingleDone = target > 0.15;
    this.finaleJingleDone = target > this.finaleTime + 0.15;
  }

  private startMusicScheduler(): void {
    if (this.musicTimer !== null) return;
    this.musicTimer = window.setInterval(() => this.scheduleAhead(), 150);
  }

  private scheduleAhead(): void {
    const now = this.currentTime();
    const horizon = now + 0.55;
    while (this.nextEventTime < horizon) {
      const t = this.nextEventTime;
      this.scheduleChordIfNeeded(t);
      this.schedulePluckIfNeeded(t);
      this.scheduleJingleIfNeeded(t);
      this.nextEventTime += 0.1;
    }
  }

  private scheduleChordIfNeeded(t: number): void {
    const index = Math.floor(t / CHORD_DURATION);
    if (index === this.lastChordIndex) return;
    this.lastChordIndex = index;
    const chord = CHORDS[index % CHORDS.length];
    const start = this.ctx.currentTime + Math.max(0, index * CHORD_DURATION - this.currentTime());
    this.playPad(chord, start);
    this.playSub(chord, start);
  }

  private schedulePluckIfNeeded(t: number): void {
    const index = Math.floor((t + 0.001) / PLUCK_STEP);
    if (index === this.lastPluckIndex) return;
    this.lastPluckIndex = index;
    const degree = PLUCK_PATTERN[index % PLUCK_PATTERN.length];
    if (degree < 0) return;
    const start = this.ctx.currentTime + Math.max(0, index * PLUCK_STEP - this.currentTime());
    this.playPluck(midiToFreq(PLUCK_SCALE[degree]), start);
  }

  private scheduleJingleIfNeeded(t: number): void {
    if (!this.openingJingleDone && t >= -0.01 && t <= 0.2) {
      this.openingJingleDone = true;
      this.playJingle(0, false);
    }
    if (!this.finaleJingleDone && this.finaleTime > 0 && t >= this.finaleTime && t < this.finaleTime + 0.2) {
      this.finaleJingleDone = true;
      this.playJingle(this.finaleTime, true);
    }
  }

  private playPad(chord: (typeof CHORDS)[number], start: number): void {
    for (const midi of chord.tones) {
      const osc = this.ctx.createOscillator();
      osc.type = "triangle";
      osc.frequency.value = midiToFreq(midi);
      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.linearRampToValueAtTime(0.048, start + 1.4);
      gain.gain.setValueAtTime(0.048, start + CHORD_DURATION - 2.2);
      gain.gain.linearRampToValueAtTime(0.0001, start + CHORD_DURATION);
      osc.connect(gain);
      gain.connect(this.padFilter);
      osc.start(start);
      osc.stop(start + CHORD_DURATION + 0.1);
      this.musicVoices.push({ src: osc, gain });
    }
  }

  private playSub(chord: (typeof CHORDS)[number], start: number): void {
    const osc = this.ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = midiToFreq(chord.root - 12);
    const gain = this.ctx.createGain();
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.linearRampToValueAtTime(0.05, start + 1.2);
    gain.gain.setValueAtTime(0.05, start + CHORD_DURATION - 2);
    gain.gain.linearRampToValueAtTime(0.0001, start + CHORD_DURATION);
    osc.connect(gain);
    gain.connect(this.musicBus);
    osc.start(start);
    osc.stop(start + CHORD_DURATION + 0.1);
    this.musicVoices.push({ src: osc, gain });
  }

  private playPluck(freq: number, start: number): void {
    const osc = this.ctx.createOscillator();
    osc.type = "triangle";
    osc.frequency.value = freq;
    const gain = this.ctx.createGain();
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.linearRampToValueAtTime(0.038, start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 1.15);
    osc.connect(gain);
    gain.connect(this.musicBus);
    const wet = this.ctx.createGain();
    wet.gain.setValueAtTime(0.045, start);
    wet.gain.exponentialRampToValueAtTime(0.0001, start + 1.4);
    gain.connect(wet);
    wet.connect(this.reverb);
    osc.start(start);
    osc.stop(start + 1.5);
    this.musicVoices.push({ src: osc, gain });
  }

  private playJingle(atPresentationTime: number, finale: boolean): void {
    const start = this.ctx.currentTime + Math.max(0, atPresentationTime - this.currentTime());
    const notes = finale ? [...JINGLE_NOTES, 84] : JINGLE_NOTES;
    notes.forEach((midi, index) => {
      const noteStart = start + index * JINGLE_STEP;
      const fundamental = midiToFreq(midi);
      [1, 2].forEach((partial) => {
        const osc = this.ctx.createOscillator();
        osc.type = "sine";
        osc.frequency.value = fundamental * partial;
        const gain = this.ctx.createGain();
        const peak = (finale ? 0.16 : 0.12) * (partial === 1 ? 1 : 0.3);
        gain.gain.setValueAtTime(0.0001, noteStart);
        gain.gain.linearRampToValueAtTime(peak, noteStart + 0.008);
        gain.gain.exponentialRampToValueAtTime(0.0001, noteStart + (finale ? 1.7 : 1.25));
        osc.connect(gain);
        gain.connect(this.musicBus);
        const wet = this.ctx.createGain();
        wet.gain.value = finale ? 0.15 : 0.11;
        gain.connect(wet);
        wet.connect(this.reverb);
        osc.start(noteStart);
        osc.stop(noteStart + 2.2);
        this.musicVoices.push({ src: osc, gain });
      });
    });

    if (finale) {
      const bass = this.ctx.createOscillator();
      bass.type = "sine";
      bass.frequency.value = midiToFreq(48);
      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.linearRampToValueAtTime(0.13, start + 0.05);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 2.6);
      bass.connect(gain);
      gain.connect(this.musicBus);
      bass.start(start);
      bass.stop(start + 2.8);
      this.musicVoices.push({ src: bass, gain });
    }
  }

  private stopNarration(): void {
    for (const source of this.narrationSources) {
      try {
        source.stop();
      } catch {
        /* already stopped */
      }
      source.disconnect();
    }
    this.narrationSources = [];
  }

  private stopMusic(): void {
    const now = this.ctx.currentTime;
    for (const voice of this.musicVoices) {
      try {
        voice.gain.gain.cancelScheduledValues(now);
        voice.gain.gain.setValueAtTime(Math.max(0.0001, voice.gain.gain.value), now);
        voice.gain.gain.linearRampToValueAtTime(0.0001, now + 0.04);
        voice.src.stop(now + 0.06);
      } catch {
        /* already stopped */
      }
    }
    this.musicVoices = [];
  }
}
