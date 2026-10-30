'use strict'
// Reference producer for the boundary-attempt observation interface (inodefence-boundary-attempt-v1).
// Runs real decompress with the callback fs functions wrapped (the node-tar effect-producer
// interposition) and emits ONE JSON stdout frame: an unordered SET of per-operation attempts,
// each tagged with its created/target region and whether it aliases a non-extraction object.
// This is the minimal, feasible subset of an entry-completion boundary (ordered per-entry
// checkpoints are NOT feasible here -- decompress writes concurrently/reordered). Region-based,
// no sentinel/CVE hardcoding (D005). Imports no InodeFence code. Driven by
// experiments/repro/decompress_entry_effect_feasibility.py.
const fs = require('node:fs')
const path = require('node:path')

const ROOT = '/work'
const EXTRACT = path.join(ROOT, 'extract')
const HARNESS = path.join(ROOT, 'archive')
const _OPERATION = { link: 'hardlink', symlink: 'symlink', writeFile: 'regular' }

const records = []
let seq = 0
function wrap(name, pathArgIndex) {
  const orig = fs[name].bind(fs)
  fs[name] = function (...args) {
    const callOrder = seq++
    const cb = args[args.length - 1]
    const target = args[pathArgIndex]
    const rec = { op: name, call_order: callOrder, src: String(args[0]), dest: String(args[pathArgIndex]) }
    const done = function (err, ...rest) {
      rec.completion_order = seq++
      rec.error = err ? err.code || String(err) : null
      try {
        const st = fs.lstatSync(target)
        rec.ino = st.dev + ':' + st.ino
      } catch (e) {
        rec.ino = null
      }
      records.push(rec)
      return typeof cb === 'function' ? cb(err, ...rest) : undefined
    }
    return orig(...args.slice(0, -1), done)
  }
}
wrap('link', 1)
wrap('symlink', 1)
wrap('writeFile', 0)

function region(absPath) {
  if (absPath === EXTRACT || absPath.startsWith(EXTRACT + '/')) return 'extraction'
  if (absPath === HARNESS || absPath.startsWith(HARNESS + '/')) return 'harness'
  return 'external'
}

// Collect (dev:ino) of every object OUTSIDE the extraction root, so aliasing is judged by
// region (any non-extraction object), never by a sentinel name.
function nonExtractionInodes() {
  const inodes = new Set()
  const walk = (dir) => {
    let ents = []
    try { ents = fs.readdirSync(dir, { withFileTypes: true }) } catch (e) { return }
    for (const e of ents) {
      const full = path.join(dir, e.name)
      if (full === EXTRACT) continue
      try { const st = fs.lstatSync(full); inodes.add(st.dev + ':' + st.ino) } catch (err) { /* ignore */ }
      if (e.isDirectory()) walk(full)
    }
  }
  walk(ROOT)
  return inodes
}

async function main() {
  const extract = EXTRACT
  const outside = path.join(ROOT, 'outside')
  fs.mkdirSync(extract, { recursive: true })
  fs.mkdirSync(outside, { recursive: true })
  const sentinel = path.join(outside, 'sentinel.txt')
  fs.writeFileSync(sentinel, Buffer.from(process.env.SENTINEL_B64, 'base64'))
  fs.chmodSync(sentinel, 0o600)
  const tar = Buffer.from(process.env.TAR_B64, 'base64')
  const version = JSON.parse(
    fs.readFileSync('/target/node_modules/decompress/package.json', 'utf8')
  ).version
  const decompress = (await import('decompress')).default
  process.chdir(ROOT)
  records.length = 0
  seq = 0
  try {
    await decompress(tar, extract)
  } catch (e) {
    /* partial extraction still observed below */
  }
  const external = nonExtractionInodes()
  const attempts = records.map((r) => {
    let targetResolved = null
    if (r.op === 'link') targetResolved = path.resolve(ROOT, r.src) // os.link resolves a relative src vs CWD
    else if (r.op === 'symlink') targetResolved = path.resolve(path.dirname(r.dest), r.src)
    const isLink = r.op === 'link' || r.op === 'symlink'
    return {
      operation: _OPERATION[r.op] || r.op,
      created_path: r.dest,
      created_region: region(r.dest),
      target_raw: isLink ? r.src : null,
      target_resolved_absolute: targetResolved,
      target_region: targetResolved === null ? 'n/a' : region(targetResolved),
      aliases_external_object: !!(r.ino && external.has(r.ino)),
      outcome: r.error === null ? 'created' : 'io_error',
    }
  })
  // Diagnostic (NOT part of the v1 contract -- consumers ignore unknown keys): the operation
  // call order, to ground the "writes are concurrent/reordered, so no ordered per-entry
  // checkpoint" finding. `attempts` itself is an unordered SET.
  const observedCallOrder = [...records]
    .sort((a, b) => a.call_order - b.call_order)
    .map((r) => _OPERATION[r.op] || r.op)
  const frame = {
    format: 'inodefence-boundary-attempt-v1',
    schema_version: 1,
    extractor: 'decompress@' + version,
    extraction_root_absolute: extract,
    attempts,
    diagnostic_observed_call_order: observedCallOrder,
  }
  process.stdout.write(JSON.stringify(frame) + '\n')
}

main().catch((e) => {
  process.stderr.write('FATAL: ' + String((e && e.message) || e) + '\n')
  process.exit(3)
})
