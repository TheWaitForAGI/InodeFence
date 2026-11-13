// Second, independent reader: load an .hwp with the rhwp engine (the open-source renderer, not the patch code),
// report page count and write one SVG per page.  usage: node render_pages.mjs <file.hwp> <outdir>
import fs from 'node:fs';
import path from 'node:path';
const [file, outdir] = process.argv.slice(2);
const vendor = (process.env.RHWP_DIR || path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', 'tool', 'scripts', 'vendor', 'rhwp'));
const rhwp = await import(path.join(vendor, 'rhwp.js'));
await rhwp.default({ module_or_path: fs.readFileSync(path.join(vendor, 'rhwp_bg.wasm')) });
// crude width model for layout: CJK and full-width glyphs = 1 em, others = 0.5 em
globalThis.measureTextWidth = (font, text) => {
  const m = /(\d+(?:\.\d+)?)px/.exec(font || ''); const px = m ? parseFloat(m[1]) : 10;
  let w = 0; for (const ch of text) w += ch.codePointAt(0) > 0x2E7F ? px : px * 0.5; return w;
};
const doc = new rhwp.HwpDocument(new Uint8Array(fs.readFileSync(file)));
const n = doc.pageCount();
fs.mkdirSync(outdir, { recursive: true });
let images = 0;
for (let p = 0; p < n; p++) {
  const svg = doc.renderPageSvg(p);
  images += (svg.match(/<image\b/g) || []).length;
  fs.writeFileSync(path.join(outdir, `page-${String(p + 1).padStart(2, '0')}.svg`), svg);
}
console.log(JSON.stringify({ file: path.basename(file), pages: n, svg_image_elements: images }));
