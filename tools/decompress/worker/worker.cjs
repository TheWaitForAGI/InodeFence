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
//   frame <archive> <dest>    extract with callback fs wrapped, emit one inodefence-boundary-attempt-v1
//                             stdout frame (set-based boundary-attempt signal for M4 self-discovery)
//   probe                     self-contained capability probe (see runProbe)
//
// Exit codes for `extract`/`frame`: 0 success, 2 extraction refused/failed (REJECTED), 3 harness/IO.
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

  if (sub === 'frame') {
    // Self-discovery (M4) observation: run real decompress with the callback fs functions
    // wrapped (the fs-wrap interposition proven feasible for decompress in
    // experiments/repro/decompress_effect_probe/fswrap_probe.cjs), and emit ONE stdout frame --
    // an unordered SET of per-operation boundary attempts (inodefence-boundary-attempt-v1). The
    // ordered, entry-correlated effect stream node-tar exposes is NOT feasible here (decompress
    // writes concurrently/reordered with no entry-context hook); this feasible set-based subset is
    // what the M3.1 boundary-attempt gradient consumes. Region-based, no sentinel/CVE hardcoding
    // (D005): the frame reports only created/target REGIONS and whether an op aliases any
    // non-extraction inode, never a sentinel name. The disposable sandbox (built by the harness)
    // already holds the sentinel; this subcommand creates nothing outside <dest>. The isolated
    // CWD is the sandbox root (parent of <dest>), exactly as `extract`, so a relative hardlink
    // target resolves against it. Exit 2 if decompress refused/failed, 0 on success; the frame is
    // emitted either way (a refused attempt is still an observed attempt).
    const archive = process.argv[3], dest = process.argv[4]
    const root = path.dirname(path.resolve(dest))
    const extractAbs = path.resolve(dest)
    const region = (abs) => {
      const r = path.resolve(abs)
      if (r === extractAbs || r.startsWith(extractAbs + path.sep)) return 'extraction'
      const rel = path.relative(root, r)
      if (rel === 'archive' || rel.startsWith('archive' + path.sep)) return 'harness'
      return 'external'
    }
    const rel = (abs) => path.relative(root, path.resolve(abs))
    const records = []
    let seq = 0
    const wrap = (name, pathArgIndex) => {
      const orig = fs[name].bind(fs)
      fs[name] = function (...args) {
        const callOrder = seq++
        const cb = args[args.length - 1]
        const rec = { op: name, call_order: callOrder, src: String(args[0]), dest: String(args[pathArgIndex]) }
        const done = function (err, ...restArgs) {
          rec.completion_order = seq++
          rec.error = err ? err.code || String(err) : null
          try { const st = fs.lstatSync(path.resolve(root, rec.dest)); rec.ino = st.dev + ':' + st.ino }
          catch (e) { rec.ino = null }
          records.push(rec)
          return typeof cb === 'function' ? cb(err, ...restArgs) : undefined
        }
        return orig(...args.slice(0, -1), done)
      }
    }
    wrap('link', 1)
    wrap('symlink', 1)
    wrap('writeFile', 0)

    const decompress = await loadDecompress(moduleName)
    process.chdir(root)
    let threw = false
    try { await decompress(fs.readFileSync(archive), dest) }
    catch (e) { threw = true; process.stderr.write(String((e && e.message) || e) + '\n') }

    // Inodes of every object OUTSIDE the extraction root, so aliasing is judged by region (any
    // non-extraction object), never by a sentinel name (D005).
    const external = new Set()
    const collect = (dir) => {
      let ents = []
      try { ents = fs.readdirSync(dir, { withFileTypes: true }) } catch (e) { return }
      for (const e of ents) {
        const full = path.join(dir, e.name)
        if (path.resolve(full) === extractAbs) continue
        try { const st = fs.lstatSync(full); external.add(st.dev + ':' + st.ino) } catch (err) { /* ignore */ }
        if (e.isDirectory()) collect(full)
      }
    }
    collect(root)

    const _OPERATION = { link: 'hardlink', symlink: 'symlink', writeFile: 'regular' }
    const attempts = records.map((r) => {
      const createdAbs = path.resolve(root, r.dest)
      const isLink = r.op === 'link' || r.op === 'symlink'
      let targetAbs = null
      if (r.op === 'link') targetAbs = path.resolve(root, r.src) // os.link resolves a relative src vs CWD (sandbox root)
      else if (r.op === 'symlink') targetAbs = path.resolve(path.dirname(createdAbs), r.src)
      return {
        operation: _OPERATION[r.op] || r.op,
        created_path: rel(createdAbs),
        created_region: region(createdAbs),
        target_raw: isLink ? r.src : null,
        target_resolved_absolute: targetAbs === null ? null : rel(targetAbs),
        target_region: targetAbs === null ? 'n/a' : region(targetAbs),
        aliases_external_object: !!(r.ino && external.has(r.ino)),
        outcome: r.error === null ? 'created' : 'io_error',
      }
    })
    // Diagnostic (NOT part of the v1 contract -- consumers ignore unknown keys): operation call
    // order, grounding the "writes are concurrent/reordered" finding; `attempts` is a SET.
    const observedCallOrder = [...records]
      .sort((a, b) => a.call_order - b.call_order)
      .map((r) => _OPERATION[r.op] || r.op)
    process.stdout.write(JSON.stringify({
      format: 'inodefence-boundary-attempt-v1',
      schema_version: 1,
      extractor: moduleName + '@' + JSON.parse(
        fs.readFileSync(path.join(__dirname, 'node_modules', ...moduleName.split('/'), 'package.json'), 'utf8')
      ).version,
      extraction_root_absolute: extractAbs,
      attempts,
      diagnostic_observed_call_order: observedCallOrder,
    }) + '\n')
    if (threw) process.exit(2)
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

  process.stderr.write('usage: worker identify|extract <archive> <dest>|frame <archive> <dest>|probe\n')
  process.exit(3)
}

main().catch(e => { process.stderr.write('FATAL: ' + String((e && e.message) || e) + '\n'); process.exit(3) })
