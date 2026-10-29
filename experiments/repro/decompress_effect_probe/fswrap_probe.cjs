'use strict'
// Feasibility probe (InodeFence M4 follow-up): observe decompress's per-operation filesystem
// effects by wrapping the callback fs functions (the same interposition the node-tar effect
// producer uses), compute each operation's boundary relevance, and report call/completion order
// so (un)ordering vs archive order is visible. Not a production observer; imports no InodeFence
// code. Driven by experiments/repro/decompress_entry_effect_feasibility.py.
const fs = require('node:fs')
const path = require('node:path')

const records = []
let seq = 0

function wrap(name, pathArgIndex) {
  const orig = fs[name].bind(fs)
  fs[name] = function (...args) {
    const callOrder = seq++
    const cb = args[args.length - 1]
    const target = args[pathArgIndex]
    const rec = {
      op: name,
      call_order: callOrder,
      src: String(args[0]),
      dest: String(args[pathArgIndex]),
      entry_context: null,
    }
    const done = function (err, ...rest) {
      rec.completion_order = seq++
      rec.error = err ? err.code || String(err) : null
      try {
        const st = fs.lstatSync(target)
        rec.result = { ino: String(st.ino), nlink: st.nlink }
      } catch (e) {
        rec.result = null
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

async function main() {
  const root = '/work'
  const extract = path.join(root, 'extract')
  const outside = path.join(root, 'outside')
  fs.mkdirSync(extract, { recursive: true })
  fs.mkdirSync(outside, { recursive: true })
  const sentinel = path.join(outside, 'sentinel.txt')
  fs.writeFileSync(sentinel, Buffer.from(process.env.SENTINEL_B64, 'base64'))
  fs.chmodSync(sentinel, 0o600)
  const sentinelIno = String(fs.lstatSync(sentinel).ino)
  const tar = Buffer.from(process.env.TAR_B64, 'base64')
  const decompress = (await import('decompress')).default
  process.chdir(root)
  records.length = 0
  seq = 0
  let error = null
  try {
    await decompress(tar, extract)
  } catch (e) {
    error = String((e && e.message) || e).slice(0, 160)
  }
  for (const r of records) {
    // Boundary relevance (set-based signal): does this op point an extract/ object outside extract/?
    let resolved = null
    if (r.op === 'link') {
      resolved = path.resolve(root, r.src) // os.link resolves a relative src against the CWD
    } else if (r.op === 'symlink') {
      resolved = path.resolve(path.dirname(r.dest), r.src) // symlink target lexically vs its dir
    }
    r.target_resolved = resolved
    r.target_region =
      resolved === null
        ? 'n/a'
        : resolved === extract || resolved.startsWith(extract + '/')
          ? 'extraction'
          : 'external'
    r.aliases_external_sentinel = !!(r.result && r.result.ino === sentinelIno)
    r.boundary_attempt = r.target_region === 'external'
  }
  process.stdout.write(JSON.stringify({ error, sentinel_ino: sentinelIno, records }) + '\n')
}

main().catch((e) => {
  process.stderr.write('FATAL: ' + String((e && e.message) || e) + '\n')
  process.exit(3)
})
