// Copy every stream of an HWP (CFB) file into a directory, using the CFB reader bundled with claw-hwp.
// Usage: node dump_hwp_streams.cjs <cfb.js> <file.hwp> <out-dir>
const fs = require("fs");
const path = require("path");
const [cfbPath, hwpPath, outDir] = process.argv.slice(2);
const CFB = require(cfbPath);
const container = CFB.read(fs.readFileSync(hwpPath), { type: "buffer" });
fs.mkdirSync(outDir, { recursive: true });
container.FullPaths.forEach((fullPath, index) => {
  const entry = container.FileIndex[index];
  if (entry.type === 2) {
    const name = path.basename(fullPath).replace(/[^\w.-]/g, "");
    fs.writeFileSync(path.join(outDir, name), Buffer.from(entry.content));
  }
});
