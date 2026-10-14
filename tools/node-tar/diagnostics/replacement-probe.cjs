// Read-only branch/checkpoint diagnostics; never a qualified native producer.
'use strict'
const fs = require('node:fs')
const crypto = require('node:crypto')
const path = require('node:path')
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex')
const [archive, destination, profile, optionsText] = process.argv.slice(2)
const modulePath = '/target/node_modules/tar'
const expected = {
  'dist/commonjs/unpack.js': '03515ed98f5df6ec0f23177b7016274f8cdc91b038d0dcd036f438a70e614eed',
  'dist/commonjs/index.min.js': 'b9464172723801f6ad013a1a819b5f31838753559d56c879202d7fb3c1326167'
}
for (const [file, digest] of Object.entries(expected)) {
  if (hash(fs.readFileSync(path.join(modulePath, file))) !== digest) throw new Error('source mismatch')
}
if (process.versions.node !== '22.22.0' || require(modulePath + '/package.json').version !== '7.5.22') {
  throw new Error('version mismatch')
}
const version = st => [st.dev, st.ino, st.nlink, st.mode, st.size, st.mtimeNs, st.ctimeNs].map(String)
const capture = filename => {
  try {
    const st = fs.lstatSync(filename, {bigint: true})
    let digest = null
    if (st.isFile()) {
      const fd = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW)
      try {
        const opened = fs.fstatSync(fd, {bigint: true})
        if (JSON.stringify(version(opened)) !== JSON.stringify(version(st))) throw new Error('object changed')
        digest = hash(fs.readFileSync(fd))
        if (JSON.stringify(version(fs.fstatSync(fd, {bigint: true}))) !== JSON.stringify(version(st))) {
          throw new Error('object changed during digest')
        }
      } finally { fs.closeSync(fd) }
    }
    const final = fs.lstatSync(filename, {bigint: true})
    if (JSON.stringify(version(final)) !== JSON.stringify(version(st))) throw new Error('object changed during capture')
    return {st_dev: String(st.dev), st_ino: String(st.ino), st_nlink: String(st.nlink),
      object_type: st.isFile() ? 'regular' : st.isDirectory() ? 'directory' : 'symlink',
      size: String(st.size), mode: Number(st.mode),
      content_digest: digest,
      link_target: st.isSymbolicLink() ? fs.readlinkSync(filename) : null}
  } catch (error) {
    if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return null
    throw error
  }
}
const tar = require(modulePath)
const records = []
const identities = new WeakMap()
let ordinal = 0
const overrides = JSON.parse(optionsText)
if (Object.keys(overrides).some(key => !['unlink', 'keep', 'newer'].includes(key)) ||
    Object.values(overrides).some(value => typeof value !== 'boolean')) throw new Error('unsupported options')
const options = {file: archive, cwd: destination, strict: true, preservePaths: false,
  ...overrides, onReadEntry: entry => {
    identities.set(entry, {ordinal: ordinal++, path: entry.path, type: entry.type,
      link_target: entry.linkpath || null})
  }}
if (profile === 'branches') {
  const symbol = description => {
    const found = Object.getOwnPropertySymbols(tar.Unpack.prototype)
      .filter(item => item.description === description)
    if (found.length !== 1) throw new Error('private symbol mismatch')
    return found[0]
  }
  const reusable = symbol('isReusable')
  const check = symbol('checkFs2')
  const originalReusable = tar.Unpack.prototype[reusable]
  const originalCheck = tar.Unpack.prototype[check]
  tar.Unpack.prototype[reusable] = function (entry, st) {
    const result = originalReusable.call(this, entry, st)
    records.push({phase: 'isReusable', entry: identities.get(entry), result,
      unlink: this.unlink, st_dev: String(st.dev), st_ino: String(st.ino),
      st_nlink: String(st.nlink), is_file: st.isFile()})
    return result
  }
  tar.Unpack.prototype[check] = function (entry, done) {
    records.push({phase: 'work_start', entry: identities.get(entry), object: capture(entry.absolute)})
    return originalCheck.call(this, entry, error => {
      // Target owns scheduling/reservation release. No extra awaits, fd pins or writes.
    records.push({phase: 'work_done', entry: identities.get(entry), object: capture(entry.absolute),
      aliases: Object.fromEntries(['a', 'alias', 'p', 'source', 'safe', 'duplicate']
        .map(name => [name, capture(path.join(destination, name))]))})
      return done(error)
    })
  }
} else if (profile !== 'stock') throw new Error('unknown profile')
;(async () => {
  let error = null
  try { await tar.x(options) } catch (caught) {
    error = {code: caught.code || caught.tarCode, message: caught.message}
  }
  console.log(JSON.stringify({records, error, node: process.versions.node,
    tar: require(modulePath + '/package.json').version}))
  process.exitCode = error ? 2 : 0
})().catch(error => { console.error(error); process.exitCode = 1 })
