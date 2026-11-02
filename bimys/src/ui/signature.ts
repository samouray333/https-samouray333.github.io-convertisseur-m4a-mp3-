// Zone de signature au doigt ou à la souris.
export class SignaturePad {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private drawing = false;
  private last: { x: number; y: number } | null = null;
  empty = true;

  constructor(initial?: string) {
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'sig-pad';
    this.canvas.width = 840;
    this.canvas.height = 300;
    this.ctx = this.canvas.getContext('2d')!;
    this.clear();
    if (initial) {
      const img = new Image();
      img.onload = () => {
        this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
        this.empty = false;
      };
      img.src = initial;
    }
    const pos = (e: PointerEvent) => {
      const r = this.canvas.getBoundingClientRect();
      return { x: ((e.clientX - r.left) / r.width) * this.canvas.width, y: ((e.clientY - r.top) / r.height) * this.canvas.height };
    };
    this.canvas.addEventListener('pointerdown', (e) => {
      this.drawing = true;
      this.last = pos(e);
      this.canvas.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    this.canvas.addEventListener('pointermove', (e) => {
      if (!this.drawing || !this.last) return;
      const p = pos(e);
      this.ctx.beginPath();
      this.ctx.moveTo(this.last.x, this.last.y);
      this.ctx.lineTo(p.x, p.y);
      this.ctx.stroke();
      this.last = p;
      this.empty = false;
    });
    const end = () => {
      this.drawing = false;
      this.last = null;
    };
    this.canvas.addEventListener('pointerup', end);
    this.canvas.addEventListener('pointercancel', end);
  }

  clear() {
    this.ctx.fillStyle = '#ffffff';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.strokeStyle = '#0a2a6b';
    this.ctx.lineWidth = 4.5;
    this.ctx.lineCap = 'round';
    this.ctx.lineJoin = 'round';
    this.empty = true;
  }

  toDataURL(): string | undefined {
    return this.empty ? undefined : this.canvas.toDataURL('image/png');
  }
}

/** Réduit une photo (max 1280 px) en JPEG pour limiter la taille stockée. */
export function resizeImage(file: File, max = 1280): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/jpeg', 0.82));
    };
    img.onerror = () => reject(new Error('Image illisible'));
    img.src = url;
  });
}
