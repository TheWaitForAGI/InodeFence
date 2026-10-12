// Benign qualification probe for node-tar's private filesystem completion callback.
// This file does not modify the installed package and is not a production adapter.
'use strict'

const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

const [
  modulePath,
  archive,
  destination,
  profile,
  expectedNode,
  expectedTar,
  expectedUnpackSha256,
  expectedEntrypointSha256
] = process.argv.slice(2)

const validProfiles = new Set(['stock', 'marker', 'snapshot'])
if (!modulePath || !archive || !destination || !validProfiles.has(profile)) {
  throw new Error(
    'usage: internal-completion-probe.cjs MODULE ARCHIVE DESTINATION ' +
    'stock|marker|snapshot EXPECTED_NODE EXPECTED_TAR EXPECTED_UNPACK_SHA256 ' +
    'EXPECTED_ENTRYPOINT_SHA256'
  )
}

const sha256 = value => crypto.createHash('sha256').update(value).digest('hex')
const packageJsonPath = path.join(modulePath, 'package.json')
const unpackPath = path.join(modulePath, 'dist/commonjs/unpack.js')
const entrypointPath = require.resolve(modulePath)
const packageValue = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'))
const actualUnpackSha256 = sha256(fs.readFileSync(unpackPath))
const actualEntrypointSha256 = sha256(fs.readFileSync(entrypointPath))

if (process.versions.node !== expectedNode) {
  throw new Error(`node version mismatch: ${process.versions.node} != ${expectedNode}`)
}
if (packageValue.version !== expectedTar) {
  throw new Error(`node-tar version mismatch: ${packageValue.version} != ${expectedTar}`)
}
if (actualUnpackSha256 !== expectedUnpackSha256) {
  throw new Error(
    `unpack.js mismatch: ${actualUnpackSha256} != ${expectedUnpackSha256}`
  )
}
if (actualEntrypointSha256 !== expectedEntrypointSha256) {
  throw new Error(
    `package entrypoint mismatch: ${actualEntrypointSha256} != ${expectedEntrypointSha256}`
  )
}

const statVersion = stat => [
  stat.dev,
  stat.ino,
  stat.mode,
  stat.nlink,
  stat.uid,
  stat.gid,
  stat.size,
  stat.mtimeMs,
  stat.ctimeMs
]

const sameVersion = (left, right) =>
  left.length === right.length && left.every((value, index) => value === right[index])

const captureObject = (absolute, relative) => {
  const before = fs.lstatSync(absolute)
  const kind = before.isFile()
    ? 'regular'
    : before.isDirectory()
      ? 'directory'
      : before.isSymbolicLink()
        ? 'symlink'
        : 'other'
  const content = kind === 'regular' ? fs.readFileSync(absolute) : null
  const linkTarget = kind === 'symlink' ? fs.readlinkSync(absolute) : null
  const after = fs.lstatSync(absolute)
  if (!sameVersion(statVersion(before), statVersion(after))) {
    throw new Error(`object changed during snapshot: ${relative}`)
  }
  return {
    path: relative,
    kind,
    dev: before.dev,
    ino: before.ino,
    nlink: before.nlink,
    mode: before.mode & 0o7777,
    uid: before.uid,
    gid: before.gid,
    size: before.size,
    mtime_ms: before.mtimeMs,
    ctime_ms: before.ctimeMs,
    link_target: linkTarget,
    content_sha256: content === null ? null : sha256(content),
    _version: statVersion(before)
  }
}

const walk = (root, current, objects) => {
  for (const name of fs.readdirSync(current).sort()) {
    const absolute = path.join(current, name)
    const relative = path.relative(root, absolute).split(path.sep).join('/')
    const observed = captureObject(absolute, relative)
    objects.push(observed)
    if (observed.kind === 'directory') walk(root, absolute, objects)
  }
}

const listTreePaths = (root, current = root, paths = []) => {
  for (const name of fs.readdirSync(current).sort()) {
    const absolute = path.join(current, name)
    const relative = path.relative(root, absolute).split(path.sep).join('/')
    paths.push(relative)
    if (fs.lstatSync(absolute).isDirectory()) listTreePaths(root, absolute, paths)
  }
  return paths
}

const snapshotTree = root => {
  const rootBefore = statVersion(fs.lstatSync(root))
  const objects = []
  walk(root, root, objects)
  const rootAfter = statVersion(fs.lstatSync(root))
  if (!sameVersion(rootBefore, rootAfter)) {
    throw new Error('extraction root changed during snapshot')
  }
  if (objects.map(object => object.path).join('\0') !== listTreePaths(root).join('\0')) {
    throw new Error('extraction tree entries changed during snapshot')
  }
  for (const object of objects) {
    const current = fs.lstatSync(path.join(root, object.path))
    if (!sameVersion(object._version, statVersion(current))) {
      throw new Error(`object changed after capture: ${object.path}`)
    }
    delete object._version
  }
  return objects
}

const semanticSnapshot = objects => objects.map(object => ({
  path: object.path,
  kind: object.kind,
  nlink: object.nlink,
  mode: object.mode,
  size: object.size,
  link_target: object.link_target,
  content_sha256: object.content_sha256
}))

const symbolsByDescription = (prototype, description) =>
  Object.getOwnPropertySymbols(prototype).filter(symbol => symbol.description === description)

const events = []
const entryIdentity = new WeakMap()
const entryErrors = new WeakMap()
const completedOrdinals = new Set()
let ordinal = 0

const tar = require(modulePath)
if (profile !== 'stock') {
  // package.json selects index.min.js. Its bundled Unpack class is distinct
  // from the readable dist/commonjs/unpack.js export, so patch the class that
  // tar.x actually constructs and guard both source artifacts above.
  const {Unpack} = tar
  const checkFs2Symbols = symbolsByDescription(Unpack.prototype, 'checkFs2')
  const onErrorSymbols = symbolsByDescription(Unpack.prototype, 'onError')
  if (checkFs2Symbols.length !== 1 || onErrorSymbols.length !== 1) {
    throw new Error('expected exactly one checkFs2 and onError private symbol')
  }
  const checkFs2 = checkFs2Symbols[0]
  const onError = onErrorSymbols[0]
  const originalCheckFs2 = Unpack.prototype[checkFs2]
  const originalOnError = Unpack.prototype[onError]

  Unpack.prototype[onError] = function (error, entry) {
    entryErrors.set(entry, `${error.name || 'Error'}: ${error.message || String(error)}`)
    return originalOnError.call(this, error, entry)
  }
  Unpack.prototype[checkFs2] = function (entry, fullyDone) {
    return originalCheckFs2.call(this, entry, error => {
      const identity = entryIdentity.get(entry)
      const completion = {
        phase: 'filesystem_effect_complete',
        monotonic_ns: process.hrtime.bigint().toString(),
        identity: identity || null,
        association_failure: identity ? null : 'entry was not observed by onReadEntry',
        target_error: entryErrors.get(entry) || (error ? String(error) : null),
        completed_ordinals: identity
          ? [...completedOrdinals, identity.ordinal].sort((left, right) => left - right)
          : [...completedOrdinals].sort((left, right) => left - right),
        snapshot: null,
        snapshot_error: null
      }
      if (identity) completedOrdinals.add(identity.ordinal)
      if (profile === 'snapshot') {
        try {
          completion.snapshot = snapshotTree(destination)
        } catch (snapshotError) {
          completion.snapshot_error =
            `${snapshotError.name || 'Error'}: ${snapshotError.message || snapshotError}`
        }
      }
      events.push(completion)
      return fullyDone(error)
    })
  }
}

const main = async () => {
  const options = {
    file: archive,
    cwd: destination,
    strict: true,
    preservePaths: false
  }
  if (profile !== 'stock') {
    options.onReadEntry = entry => {
      const identity = {
        ordinal: ordinal++,
        path: entry.path,
        type: entry.type,
        link_target: entry.linkpath || null
      }
      entryIdentity.set(entry, identity)
      events.push({
        phase: 'archive_entry_read',
        monotonic_ns: process.hrtime.bigint().toString(),
        identity
      })
    }
  }

  const started = process.hrtime.bigint()
  await tar.x(options)
  const completed = process.hrtime.bigint()
  const finalSnapshot = snapshotTree(destination)
  process.stdout.write(JSON.stringify({
    schema_version: 1,
    profile,
    node_version: process.versions.node,
    tar_version: packageValue.version,
    unpack_sha256: actualUnpackSha256,
    package_entrypoint: entrypointPath,
    package_entrypoint_sha256: actualEntrypointSha256,
    target_duration_ns: Number(completed - started),
    events,
    final_snapshot: finalSnapshot,
    final_semantic_snapshot: semanticSnapshot(finalSnapshot)
  }) + '\n')
}

main().catch(error => {
  process.stderr.write(String(error.stack || error) + '\n')
  process.exitCode = 1
})
