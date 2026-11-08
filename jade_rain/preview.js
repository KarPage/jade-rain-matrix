/* Playback of the Python renderer's masks and scene, at desktop loop timing. */
class RainPreview {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d', {alpha: false});
    this.lightBuffer = document.createElement('canvas');
    this.cache = new Map();
    this.paused = false;
    this.motion = matchMedia('(prefers-reduced-motion: reduce)');
    this.motion.addEventListener('change', () => this.wake());
    document.addEventListener('visibilitychange', () => this.wake());
  }
  async setScene(scene, isCurrent = () => true) {
    const atlas = new Image();
    atlas.src = scene.atlas;
    await atlas.decode();
    if (!isCurrent()) return;
    this.scene = scene;
    this.atlas = atlas;
    this.cache.clear();
    this.canvas.width = this.lightBuffer.width = scene.width;
    this.canvas.height = this.lightBuffer.height = scene.height;
    this.start = performance.now();
    this.wake();
  }
  wake() {
    cancelAnimationFrame(this.raf);
    if (!this.scene || document.hidden) return;
    const tick = (now) => {
      if (!this.last || now - this.last >= 1000 / 24) {
        const still = this.scene.mode === 'still' || this.paused || this.motion.matches;
        const t = still ? 160 : ((now - this.start) * 24 / 1000 + 160) % this.scene.frames;
        this.draw(t);
        this.last = now;
      }
      if (this.scene.mode !== 'still' && !this.paused && !this.motion.matches && !document.hidden)
        this.raf = requestAnimationFrame(tick);
    };
    this.last = 0;
    this.raf = requestAnimationFrame(tick);
  }
  sample(fraction) {
    const ramp = this.scene.ramp;
    const scaled = Math.max(0, Math.min(1, fraction)) * (ramp.length - 1);
    const index = Math.min(Math.floor(scaled), ramp.length - 2), blend = scaled - index;
    return ramp[index].map((v, i) => v * (1 - blend) + ramp[index + 1][i] * blend);
  }
  blit(ctx, id, x, y, color) {
    const [sx, sy, w, h] = this.scene.boxes[id];
    if (x >= this.canvas.width || y >= this.canvas.height || x + w < 0 || y + h < 0) return;
    // Small quantization keeps tint caches bounded without changing the scene.
    const rgb = color.map(v => Math.min(255, Math.max(0, Math.round(v / 16) * 16)));
    const key = `${id}:${rgb.join(',')}`;
    let sprite = this.cache.get(key);
    if (!sprite) {
      sprite = document.createElement('canvas'); sprite.width = w; sprite.height = h;
      const c = sprite.getContext('2d');
      c.drawImage(this.atlas, sx, sy, w, h, 0, 0, w, h);
      c.globalCompositeOperation = 'source-in';
      c.fillStyle = `rgb(${rgb.join(',')})`; c.fillRect(0, 0, w, h);
      if (this.cache.size > 6000) this.cache.clear();
      this.cache.set(key, sprite);
    }
    ctx.drawImage(sprite, Math.round(x), Math.round(y));
  }
  draw(t) {
    const s = this.scene, ctx = this.ctx, cycle = t / s.frames * s.cycles;
    const isLight = Math.max(...s.background) > 140;
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = `rgb(${s.background.join(',')})`;
    ctx.fillRect(0, 0, s.width, s.height);
    const target = isLight ? this.lightBuffer.getContext('2d', {willReadFrequently: true}) : ctx;
    if (isLight) { target.clearRect(0, 0, s.width, s.height); }
    target.globalCompositeOperation = 'lighter';
    const multiply = (color, gain) => color.map(v => v * gain);
    for (const logo of s.logos) {
      const h = s.boxes[logo.id][3];
      this.blit(target, logo.id, logo.x, Math.round(((logo.phase + cycle) % 1) * logo.travel) - h, logo.color);
    }
    for (const stream of s.streams) {
      const sprites = s.rain[stream.layer], wordSets = s.words[stream.layer];
      const head = (stream.phase + stream.period * cycle) % stream.period;
      const rowHead = Math.floor(head), frac = head - rowHead, span = stream.tail + 1;
      for (let depth = 0; depth < span; depth++) {
        const row = rowHead - depth;
        if (row < 0 || row >= stream.rows) continue;
        const f = (depth + frac) / span;
        let color = depth === 0 ? multiply(s.ramp[0], .45 + .55 * frac)
          : depth === 1 ? s.ramp[0].map((v,i) => v * (1-frac) + this.sample(f)[i] * frac)
          : multiply(this.sample(f), (1-f) ** .6);
        color = multiply(color, stream.gain);
        const step = Math.floor((t * stream.change + rainMix(stream.seed, row)) / s.frames);
        const turn = step % stream.change;
        let glyph = stream.words[row];
        const steady = glyph && (glyph.name || glyph.steady);
        if (glyph && !steady && rainMix(stream.seed, row, turn, 3) % 11 === 0) glyph = null;
        if (glyph && depth > 1) {
          const along = f * (steady ? .45 : .6);
          color = multiply(this.sample(along), ((1-along) ** (steady ? .5 : .6)) * stream.gain * (steady ? 1.45 : 1.3));
        }
        let id = sprites.ids[rainMix(stream.seed, row, turn) % sprites.ids.length], pad = sprites.pad;
        if (glyph && wordSets[glyph.scale].ids[glyph.char] !== undefined) {
          id = wordSets[glyph.scale].ids[glyph.char]; pad = wordSets[glyph.scale].pad;
        }
        this.blit(target, id, stream.x - pad, row * stream.cell - pad, color);
        if (depth <= 1) {
          const glow = s.glows[stream.layer], half = Math.floor(s.boxes[glow][3] / 2);
          this.blit(target, glow, stream.x + Math.floor(stream.cell/2) - half, row * stream.cell + Math.floor(stream.cell/2) - half,
            multiply(s.glowColor, (depth === 0 ? frac : 1-frac) * .4 * stream.gain));
        }
      }
      if (s.logoSprite && stream.seed % 11 === 0) {
        const logo = s.logoSprite, box = s.boxes[logo.id];
        this.blit(target, logo.id, stream.x - Math.floor(box[2]/2), rowHead * stream.cell - Math.floor(box[3]/2), logo.color);
      }
    }
    if (isLight) {
      // Same ink-on-light-field equation as Scene.frame, not a different theme.
      const pixels = target.getImageData(0,0,s.width,s.height), bg = s.background, ink = s.ramp[2];
      for (let p=0; p<pixels.data.length; p+=4) {
        const alpha = pixels.data[p+3]/255;
        const coverage = Math.min(1, Math.max(pixels.data[p],pixels.data[p+1],pixels.data[p+2]) * alpha / 18);
        for(let c=0;c<3;c++) pixels.data[p+c] = bg[c]*(1-coverage)+ink[c]*coverage;
        pixels.data[p+3] = 255;
      }
      ctx.putImageData(pixels,0,0);
    }
    this.canvas.dataset.frame = String(t);
  }
}
function rainMix(...parts) {
  let value = 0x811c9dc5;
  for (const part of parts) value = Math.imul((value ^ part) >>> 0, 0x01000193) >>> 0;
  return value;
}
