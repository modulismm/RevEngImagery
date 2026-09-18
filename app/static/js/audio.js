/* Imagery audio engine.
 *
 * A faithful reproduction of the original app's Web Audio graph, recovered from
 * its shipped bundle. Constants here are not taste -- they are what the original
 * used, so existing canvases sound the same. See ../../docs/schema.md.
 *
 *   input -> lowshelf 320Hz   (gain = effects.lowFreq)
 *         -> peaking 1000Hz Q=1 (gain = effects.midFreq)
 *         -> highshelf 3200Hz (gain = effects.highFreq)
 *         -> dry gain (1-k) ----.
 *          \-> convolver -> wet gain (k) --+-> master -> destination
 *
 * k = effects.reverbLevel / 100.
 */

export const LOW_SHELF_HZ = 320;
export const PEAKING_HZ = 1000;
export const PEAKING_Q = 1;
export const HIGH_SHELF_HZ = 3200;
export const REVERB_SECONDS = 2;
export const SMOOTHING_TC = 0.05;   // setTargetAtTime time constant on approach
export const FADE_OUT = 0.2;        // linear ramp to silence on leaving a zone
export const DEFAULT_VOLUME = 0.7;

/** Pitch is plain resampling: duration changes with pitch, as in the original. */
export function playbackRateFor(semitones) {
  return Math.pow(2, (Number(semitones) || 0) / 12);
}

/**
 * The reverb impulse is generated, not loaded: white noise under a squared
 * decay envelope. Two channels, two seconds.
 */
export function makeImpulse(ctx) {
  const length = Math.floor(ctx.sampleRate * REVERB_SECONDS);
  const buffer = ctx.createBuffer(2, length, ctx.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const data = buffer.getChannelData(ch);
    for (let i = 0; i < length; i++) {
      data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 2);
    }
  }
  return buffer;
}

/** Build the per-zone effects chain. Returns { input, output, masterGain }. */
export function createChain(ctx, effects = {}, impulse = null) {
  const input = ctx.createGain();
  const low = ctx.createBiquadFilter();
  const mid = ctx.createBiquadFilter();
  const high = ctx.createBiquadFilter();
  const convolver = ctx.createConvolver();
  const dry = ctx.createGain();
  const wet = ctx.createGain();
  const master = ctx.createGain();

  low.type = 'lowshelf';
  low.frequency.value = LOW_SHELF_HZ;
  low.gain.value = effects.lowFreq || 0;

  mid.type = 'peaking';
  mid.frequency.value = PEAKING_HZ;
  mid.Q.value = PEAKING_Q;
  mid.gain.value = effects.midFreq || 0;

  high.type = 'highshelf';
  high.frequency.value = HIGH_SHELF_HZ;
  high.gain.value = effects.highFreq || 0;

  convolver.buffer = impulse || makeImpulse(ctx);

  const k = (Number(effects.reverbLevel) || 0) / 100;
  dry.gain.value = 1 - k;
  wet.gain.value = k;
  master.gain.setValueAtTime(0, ctx.currentTime);

  input.connect(low);
  low.connect(mid);
  mid.connect(high);
  high.connect(dry);
  high.connect(convolver);
  convolver.connect(wet);
  dry.connect(master);
  wet.connect(master);

  return { input, output: master, masterGain: master, nodes: { low, mid, high, dry, wet } };
}

/**
 * Volume for a pointer at `distance` from a zone centre.
 * Linear falloff: full at the centre, silent at the edge. The audible radius is
 * `zone.radius / 2` -- the stored field holds a diameter.
 */
export function gainForDistance(zone, distance) {
  const reach = (Number(zone.radius) || 0) / 2;
  if (reach <= 0 || distance > reach) return 0;
  const volume = zone.volume == null ? DEFAULT_VOLUME : Number(zone.volume);
  return volume * (1 - Math.min(1, distance / reach));
}

export function isInside(zone, distance) {
  return distance <= (Number(zone.radius) || 0) / 2;
}

/**
 * Plays a canvas's zones in response to pointer position.
 *
 * One <audio> element per zone, routed through its own chain -- matching the
 * original, which used media elements rather than buffer sources for custom
 * sounds. Elements are created lazily so a canvas with many zones does not
 * fetch everything up front.
 */
export class ZonePlayer {
  constructor() {
    this.ctx = null;
    this.impulse = null;
    this.zones = [];
    this.tracks = new Map();   // zone id -> { el, chain, source, playing }
    this.inside = new Set();
  }

  /** Must be called from a user gesture; browsers block audio otherwise. */
  unlock() {
    if (!this.ctx) {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return false;
      this.ctx = new Ctor();
      this.impulse = makeImpulse(this.ctx);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx.state === 'running';
  }

  get ready() {
    return !!this.ctx && this.ctx.state === 'running';
  }

  setZones(zones) {
    const keep = new Set((zones || []).map((z) => z.id));
    for (const [id, track] of this.tracks) {
      if (!keep.has(id)) { this._stop(id, track, true); this.tracks.delete(id); }
    }
    this.zones = zones || [];
    // Effects can change while editing; rebuild chains for zones we already hold.
    for (const zone of this.zones) {
      const track = this.tracks.get(zone.id);
      if (track) this._applyEffects(track, zone);
    }
  }

  _track(zone) {
    let track = this.tracks.get(zone.id);
    if (track || !zone.url || !this.ctx) return track;

    const el = new Audio();
    el.crossOrigin = 'anonymous';
    el.preload = 'auto';
    el.loop = false;
    el.src = zone.url;

    const source = this.ctx.createMediaElementSource(el);
    const chain = createChain(this.ctx, zone.effects || {}, this.impulse);
    source.connect(chain.input);
    chain.output.connect(this.ctx.destination);

    // Loop within the trimmed window, as the original did on timeupdate.
    el.addEventListener('timeupdate', () => {
      const end = Number(zone.endTime) || 0;
      if (end && el.currentTime >= end) el.currentTime = Number(zone.startTime) || 0;
    });

    track = { el, chain, source, playing: false, zoneId: zone.id };
    this.tracks.set(zone.id, track);
    return track;
  }

  _applyEffects(track, zone) {
    const fx = zone.effects || {};
    const { low, mid, high, dry, wet } = track.chain.nodes;
    low.gain.value = fx.lowFreq || 0;
    mid.gain.value = fx.midFreq || 0;
    high.gain.value = fx.highFreq || 0;
    const k = (Number(fx.reverbLevel) || 0) / 100;
    dry.gain.value = 1 - k;
    wet.gain.value = k;
    track.el.playbackRate = playbackRateFor(fx.pitch);
  }

  /** Pointer moved to (x, y) in the same units as zone.x/zone.y. */
  update(x, y, toPixels) {
    if (!this.ready) return;
    const now = this.ctx.currentTime;
    for (const zone of this.zones) {
      if (!zone.url) continue;
      const centre = toPixels(zone.x, zone.y);
      const distance = Math.hypot(x - centre.x, y - centre.y);
      const track = isInside(zone, distance) ? this._track(zone) : this.tracks.get(zone.id);
      if (!track) continue;

      if (isInside(zone, distance)) {
        if (!this.inside.has(zone.id)) {
          this.inside.add(zone.id);
          track.el.currentTime = Number(zone.startTime) || 0;
          track.el.playbackRate = playbackRateFor((zone.effects || {}).pitch);
          const p = track.el.play();
          if (p && p.catch) p.catch(() => { track.playing = false; });
          track.playing = true;
        }
        track.chain.masterGain.gain.setTargetAtTime(
          gainForDistance(zone, distance), now, SMOOTHING_TC);
      } else if (this.inside.has(zone.id)) {
        this.inside.delete(zone.id);
        this._stop(zone.id, track, false);
      }
    }
  }

  _stop(id, track, immediate) {
    if (!track) return;
    this.inside.delete(id);
    if (this.ctx) {
      const g = track.chain.masterGain.gain;
      if (immediate) g.value = 0;
      else g.linearRampToValueAtTime(0, this.ctx.currentTime + FADE_OUT);
    }
    const pause = () => { try { track.el.pause(); } catch (_) {} track.playing = false; };
    if (immediate) pause(); else setTimeout(pause, FADE_OUT * 1000 + 50);
  }

  /** Leaving the image: silence everything. */
  allOff() {
    for (const [id, track] of this.tracks) this._stop(id, track, false);
  }

  destroy() {
    for (const [id, track] of this.tracks) this._stop(id, track, true);
    this.tracks.clear();
    if (this.ctx) { this.ctx.close(); this.ctx = null; }
  }
}
