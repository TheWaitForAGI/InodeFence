// Target-specific decompress extraction worker for InodeFence generality (M4.2).
//
// It drives the decompress npm package (original kevva/decompress, CJS) or its maintained
// fork @xhmikosr/decompress (ESM) -- whichever this image pins -- both loaded by dynamic
// import (.default is module.exports for CJS, the default export for ESM). InodeFence's
// generic model/oracle are NOT imported here: the worker only invokes the third-party
// extractor and reports raw bytes/outcome. The Observer and Oracle judge the result unchanged.
//
// The pinned package is auto-detected from this image's /target/package.json (exactly one
// decompress dependency per role), so no env var or arg is needed and the production backend's
// env scrubbing is irrelevant.
//
// Subcommands:
//   identify                  print JSON {decompress_module, decompress_version, node_version, worker_sha256}
//   extract <archive> <dest>  extract <archive> into <dest> via decompress
//   probe                     self-contained capability probe (see runProbe)
//
// Exit codes for `extract`: 0 success, 2 extraction refused/failed (REJECTED), 3 harness/IO.
'use strict'
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')

// The single decompress dependency this image installed (original 'decompress' for the
// affected role, '@xhmikosr/decompress' for the fixed role).
function detectModule() {
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'))
  const deps = Object.keys(pkg.dependencies || {})
  const found = deps.find(d => d === 'decompress' || d.endsWith('/decompress'))
  if (!found) throw new Error('no decompress dependency found in /target/package.json')
  return found
}

async function loadDecompress(moduleName) {
  const mod = await import(moduleName)
  return mod.default ?? mod
}

function lstat(p) {
  try {
    const s = fs.lstatSync(p)
    return {
      dev: String(s.dev), ino: String(s.ino), nlink: s.nlink,
      type: s.isSymbolicLink() ? 'sym' : s.isDirectory() ? 'dir' : s.isFile() ? 'reg' : 'other',
      size: s.size,
    }
  } catch (e) { return null }
}

function walk(dir, base) {
  const out = {}
  let ents
  try { ents = fs.readdirSync(dir) } catch (e) { return out }
  for (const n of ents) {
    const full = path.join(dir, n)
    const rel = base ? base + '/' + n : n
    const s = lstat(full)
    out[rel] = s
    if (s && s.type === 'dir') Object.assign(out, walk(full, rel))
  }
  return out
}

async function main() {
  const sub = process.argv[2]
  const moduleName = detectModule()

  if (sub === 'identify') {
    // Read the version from the installed package.json via fs: the ESM fork's exports map
    // blocks require('<pkg>/package.json').
    const pkgPath = path.join(__dirname, 'node_modules', ...moduleName.split('/'), 'package.json')
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'))
    const self = fs.readFileSync(__filename)
    process.stdout.write(JSON.stringify({
      decompress_module: moduleName,
      decompress_version: pkg.version,
      node_version: process.versions.node,
      worker_sha256: crypto.createHash('sha256').update(self).digest('hex'),
    }))
    return
  }

  if (sub === 'extract') {
    const archive = process.argv[3], dest = process.argv[4]
    const decompress = await loadDecompress(moduleName)
    // Isolated CWD: the extractor runs from the disposable sandbox root (the parent of the
    // extraction root), mirroring a caller that extracts into a subdirectory. A relative
    // hardlink target is then resolved by fs.link against this working directory.
    process.chdir(path.dirname(dest))
    try { await decompress(fs.readFileSync(archive), dest) }
    catch (e) { process.stderr.write(String((e && e.message) || e) + '\n'); process.exit(2) }
    return
  }

  if (sub === 'probe') {
    const root = '/work', extract = path.join(root, 'extract'), outside = path.join(root, 'outside')
    fs.mkdirSync(extract, { recursive: true })
    fs.mkdirSync(outside, { recursive: true })
    const sentinel = path.join(outside, 'sentinel.txt')
    fs.writeFileSync(sentinel, Buffer.from(process.env.SENTINEL_B64, 'base64'))
    fs.chmodSync(sentinel, 0o600)
    const tar = Buffer.from(process.env.TAR_B64, 'base64')
    const decompress = await loadDecompress(moduleName)
    process.chdir(root)
    const before = lstat(sentinel)
    let declined = null
    try { await decompress(tar, extract) }
    catch (e) { declined = { message: String((e && e.message) || e).slice(0, 200) } }
    const after = lstat(sentinel)
    const tree = walk(extract, '')
    const shared = []
    if (after) for (const k in tree) { const o = tree[k]; if (o && o.dev === after.dev && o.ino === after.ino) shared.push('extract/' + k) }
    process.stdout.write(JSON.stringify({
      decompress_module: moduleName,
      declined, reference_before: before, reference_after: after,
      nlink_before: before && before.nlink, nlink_after: after && after.nlink,
      shared_identity: shared, extract_tree: tree,
    }) + '\n')
    return
  }

  process.stderr.write('usage: worker identify|extract <archive> <dest>|probe\n')
  process.exit(3)
}

main().catch(e => { process.stderr.write('FATAL: ' + String((e && e.message) || e) + '\n'); process.exit(3) })
