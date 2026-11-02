// Générateur de rapports PDF (jsPDF + jspdf-autotable) avec police Unicode embarquée.
import { jsPDF } from 'jspdf';
import autoTable, { type RowInput, type UserOptions } from 'jspdf-autotable';
import regularUrl from '../assets/fonts/DejaVuSansCondensed.ttf?url';
import boldUrl from '../assets/fonts/DejaVuSansCondensed-Bold.ttf?url';
import type { Settings } from '../store/db';
import { dateFr, today } from '../core/format';

const PETROL: [number, number, number] = [15, 76, 92];
const ORANGE: [number, number, number] = [242, 140, 40];
let fontCache: { regular: string; bold: string } | null = null;

async function b64(url: string): Promise<string> {
  const buf = new Uint8Array(await (await fetch(url)).arrayBuffer());
  let s = '';
  for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(s);
}

async function fonts() {
  if (!fontCache) fontCache = { regular: await b64(regularUrl), bold: await b64(boldUrl) };
  return fontCache;
}

export class Report {
  doc: jsPDF;
  y: number;
  readonly margin = 14;
  readonly top = 30;
  private title: string;
  private subtitle: string;
  private settings: Settings;

  private constructor(doc: jsPDF, title: string, subtitle: string, settings: Settings) {
    this.doc = doc;
    this.title = title;
    this.subtitle = subtitle;
    this.settings = settings;
    this.y = this.top;
  }

  static async create(title: string, subtitle: string, settings: Settings, landscape = false): Promise<Report> {
    const doc = new jsPDF({ unit: 'mm', format: 'a4', orientation: landscape ? 'landscape' : 'portrait' });
    const f = await fonts();
    doc.addFileToVFS('DejaVu.ttf', f.regular);
    doc.addFont('DejaVu.ttf', 'DejaVu', 'normal');
    doc.addFileToVFS('DejaVu-Bold.ttf', f.bold);
    doc.addFont('DejaVu-Bold.ttf', 'DejaVu', 'bold');
    doc.setFont('DejaVu', 'normal');
    doc.setProperties({ title, subject: subtitle, creator: 'Bimys (QMTech)', author: settings.etablissement || 'Bimys' });
    return new Report(doc, title, subtitle, settings);
  }

  get width(): number {
    return this.doc.internal.pageSize.getWidth();
  }

  get height(): number {
    return this.doc.internal.pageSize.getHeight();
  }

  get inner(): number {
    return this.width - 2 * this.margin;
  }

  ensure(h: number) {
    if (this.y + h > this.height - 16) {
      this.doc.addPage();
      this.y = this.top;
    }
  }

  h2(text: string) {
    this.ensure(14);
    this.y += 2;
    this.doc.setFont('DejaVu', 'bold');
    this.doc.setFontSize(12);
    this.doc.setTextColor(...PETROL);
    this.doc.text(text, this.margin, this.y + 4);
    this.doc.setDrawColor(...ORANGE);
    this.doc.setLineWidth(0.6);
    this.doc.line(this.margin, this.y + 6, this.margin + 18, this.y + 6);
    this.y += 10;
    this.doc.setTextColor(30, 30, 30);
    this.doc.setFont('DejaVu', 'normal');
  }

  para(text: string, size = 9.5, color: [number, number, number] = [40, 40, 40]) {
    this.doc.setFontSize(size);
    this.doc.setTextColor(...color);
    const lines = this.doc.splitTextToSize(text, this.inner) as string[];
    for (const l of lines) {
      this.ensure(5);
      this.doc.text(l, this.margin, this.y + 3.5);
      this.y += size * 0.45;
    }
    this.y += 1.5;
    this.doc.setTextColor(30, 30, 30);
  }

  kv(rows: [string, string][], cols = 2) {
    const body: RowInput[] = [];
    for (let i = 0; i < rows.length; i += cols) {
      const r: string[] = [];
      for (let c = 0; c < cols; c++) r.push(rows[i + c]?.[0] ?? '', rows[i + c]?.[1] ?? '');
      body.push(r);
    }
    const colStyles: Record<number, any> = {};
    for (let c = 0; c < cols; c++) colStyles[c * 2] = { fontStyle: 'bold', textColor: PETROL, cellWidth: 34 };
    this.table([], body, { theme: 'plain', styles: { fontSize: 8.5, cellPadding: 1.2 }, columnStyles: colStyles });
  }

  table(head: string[], body: RowInput[], opts: Partial<UserOptions> = {}) {
    autoTable(this.doc, {
      head: head.length ? [head] : undefined,
      body,
      startY: this.y,
      margin: { left: this.margin, right: this.margin, top: this.top, bottom: 16 },
      theme: 'striped',
      ...opts,
      styles: { font: 'DejaVu', fontSize: 8.5, cellPadding: 1.6, overflow: 'linebreak', ...(opts.styles ?? {}) },
      headStyles: { fillColor: PETROL, textColor: 255, fontStyle: 'bold', ...(opts.headStyles ?? {}) },
      alternateRowStyles: { fillColor: [244, 247, 248] },
    });
    this.y = ((this.doc as any).lastAutoTable?.finalY ?? this.y) + 5;
  }

  image(dataUrl: string, w: number, h: number, x = this.margin) {
    this.ensure(h + 2);
    try {
      const fmt = dataUrl.startsWith('data:image/png') ? 'PNG' : 'JPEG';
      this.doc.addImage(dataUrl, fmt, x, this.y, w, h);
    } catch {
      this.para('(image illisible)');
    }
    this.y += h + 3;
  }

  /** Dessine en-tête et pied de page sur toutes les pages. */
  private decorate() {
    const n = this.doc.getNumberOfPages();
    const s = this.settings;
    for (let i = 1; i <= n; i++) {
      this.doc.setPage(i);
      const W = this.width;
      this.doc.setFillColor(...PETROL);
      this.doc.rect(0, 0, W, 4, 'F');
      this.doc.setFillColor(...ORANGE);
      this.doc.rect(0, 4, W, 0.9, 'F');
      let x = this.margin;
      if (s.logo) {
        try {
          const fmt = s.logo.startsWith('data:image/png') ? 'PNG' : 'JPEG';
          const p = this.doc.getImageProperties(s.logo);
          const h = 14;
          const w = Math.min(36, (p.width / p.height) * h);
          this.doc.addImage(s.logo, fmt, x, 8, w, h);
          x += w + 4;
        } catch {
          /* logo ignoré */
        }
      }
      this.doc.setFont('DejaVu', 'bold');
      this.doc.setFontSize(10);
      this.doc.setTextColor(...PETROL);
      this.doc.text(s.etablissement || 'Bimys', x, 12);
      this.doc.setFont('DejaVu', 'normal');
      this.doc.setFontSize(8);
      this.doc.setTextColor(90, 90, 90);
      if (s.adresse) this.doc.text(s.adresse, x, 16);
      this.doc.setFont('DejaVu', 'bold');
      this.doc.setFontSize(13);
      this.doc.setTextColor(20, 20, 20);
      this.doc.text(this.title, W - this.margin, 12, { align: 'right' });
      this.doc.setFont('DejaVu', 'normal');
      this.doc.setFontSize(8.5);
      this.doc.setTextColor(90, 90, 90);
      const sub = this.doc.splitTextToSize(this.subtitle, 110) as string[];
      this.doc.text(sub.slice(0, 2), W - this.margin, 17, { align: 'right' });
      this.doc.setDrawColor(210, 215, 218);
      this.doc.setLineWidth(0.2);
      this.doc.line(this.margin, 25, W - this.margin, 25);
      // pied de page
      const H = this.height;
      this.doc.setFontSize(7.5);
      this.doc.setTextColor(120, 120, 120);
      this.doc.text(`Bimys (QMTech) : document généré le ${dateFr(today())}`, this.margin, H - 8);
      this.doc.text(`Page ${i} / ${n}`, W - this.margin, H - 8, { align: 'right' });
    }
  }

  output(): Uint8Array {
    this.decorate();
    return new Uint8Array(this.doc.output('arraybuffer'));
  }
}
