// Benign qualification probe for causally attributed node-tar filesystem effects.
// This file does not modify the installed package and is not a production adapter.
'use strict'

const {AsyncLocalStorage} = require('node:async_hooks')
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

const validProfiles = new Set(['stock', 'context', 'effects'])
if (!modulePath || !archive || !destination || !validProfiles.has(profile)) {
  throw new Error(
    'usage: causal-effect-probe.cjs MODULE ARCHIVE DESTINATION ' +
    'stock|context|effects EXPECTED_NODE EXPECTED_TAR EXPECTED_UNPACK_SHA256 ' +
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
  throw new Error(`unpack.js mismatch: ${actualUnpackSha256} != ${expectedUnpackSha256}`)
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
    throw new Error(`object changed during final snapshot: ${relative}`)
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
    throw new Error('extraction root changed during final snapshot')
  }
  if (objects.map(object => object.path).join('\0') !== listTreePaths(root).join('\0')) {
    throw new Error('extraction tree entries changed during final snapshot')
  }
  for (const object of objects) {
    const current = fs.lstatSync(path.join(root, object.path))
    if (!sameVersion(object._version, statVersion(current))) {
      throw new Error(`object changed after final capture: ${object.path}`)
    }
    delete object._version
  }
  return objects
}

const semanticSnapshot = objects => {
  const identityMembers = new Map()
  for (const object of objects) {
    const key = `${object.dev}:${object.ino}`
    const members = identityMembers.get(key) || []
    members.push(object.path)
    identityMembers.set(key, members)
  }
  return objects.map(object => {
    const members = identityMembers.get(`${object.dev}:${object.ino}`).sort()
    return {
      path: object.path,
      kind: object.kind,
      identity_group: members.length > 1 ? members : [],
      nlink: object.nlink,
      mode: object.mode,
      size: object.size,
      link_target: object.link_target,
      content_sha256: object.content_sha256
    }
  })
}

const symbolsByDescription = (prototype, description) =>
  Object.getOwnPropertySymbols(prototype).filter(symbol => symbol.description === description)

const entryContext = new AsyncLocalStorage()
const entryIdentity = new WeakMap()
const entryErrors = new WeakMap()
const fdOwners = new Map()
const events = []
const observationFailures = []
let ordinal = 0
let operationSequence = 0
let recordingEffects = false

const normalizedPath = value => {
  if (typeof value === 'string' || Buffer.isBuffer(value)) {
    return path.resolve(String(value))
  }
  if (value instanceof URL && value.protocol === 'file:') return path.resolve(value.pathname)
  return null
}

const withinDestination = value => {
  const normalized = normalizedPath(value)
  return normalized !== null &&
    (normalized === destination || normalized.startsWith(`${destination}${path.sep}`))
}

const relativePath = value => {
  const normalized = normalizedPath(value)
  return normalized !== null && withinDestination(normalized)
    ? path.relative(destination, normalized).split(path.sep).join('/') || '.'
    : null
}

const operationSpecs = {
  open: {pathIndexes: [0], fdIndex: null},
  write: {pathIndexes: [], fdIndex: 0},
  writev: {pathIndexes: [], fdIndex: 0},
  close: {pathIndexes: [], fdIndex: 0},
  mkdir: {pathIndexes: [0], fdIndex: null},
  chmod: {pathIndexes: [0], fdIndex: null},
  chown: {pathIndexes: [0], fdIndex: null},
  utimes: {pathIndexes: [0], fdIndex: null},
  futimes: {pathIndexes: [], fdIndex: 0},
  fchown: {pathIndexes: [], fdIndex: 0},
  unlink: {pathIndexes: [0], fdIndex: null},
  rmdir: {pathIndexes: [0], fdIndex: null},
  link: {pathIndexes: [0, 1], fdIndex: null},
  symlink: {pathIndexes: [1], fdIndex: null},
  rename: {pathIndexes: [0, 1], fdIndex: null},
  rm: {pathIndexes: [0], fdIndex: null}
}

const sameIdentity = (left, right) =>
  left !== null && right !== null &&
  left.ordinal === right.ordinal && left.path === right.path &&
  left.type === right.type && left.link_target === right.link_target

const installEffectWrappers = () => {
  for (const [name, spec] of Object.entries(operationSpecs)) {
    const original = fs[name]
    if (typeof original !== 'function') continue
    fs[name] = function (...args) {
      const callbackIndex = args.findLastIndex(value => typeof value === 'function')
      if (callbackIndex === -1) return original.apply(this, args)
      const requestedIdentity = entryContext.getStore() || null
      const requestedPaths = spec.pathIndexes
        .map(index => relativePath(args[index]))
        .filter(value => value !== null)
      const fd = spec.fdIndex === null ? null : args[spec.fdIndex]
      const requestedOwner = typeof fd === 'number' ? fdOwners.get(fd) || null : null
      const relevant = requestedPaths.length > 0 || requestedOwner !== null
      const operationId = operationSequence++
      const requestedNs = process.hrtime.bigint().toString()
      const callback = args[callbackIndex]
      args[callbackIndex] = function (...callbackArgs) {
        const error = callbackArgs[0] || null
        let owner = requestedOwner
        if (name === 'open' && !error && typeof callbackArgs[1] === 'number' && relevant) {
          owner = {
            identity: requestedIdentity,
            path: requestedPaths[0] || null
          }
          fdOwners.set(callbackArgs[1], owner)
        }
        const ownerIdentity = owner === null ? null : owner.identity
        if (requestedIdentity !== null && ownerIdentity !== null &&
            !sameIdentity(requestedIdentity, ownerIdentity)) {
          observationFailures.push({
            kind: 'identity_conflict',
            operation: name,
            requested_identity: requestedIdentity,
            fd_owner_identity: ownerIdentity
          })
        }
        const identity = requestedIdentity || ownerIdentity
        const paths = requestedPaths.length > 0
          ? requestedPaths
          : owner !== null && owner.path !== null
            ? [owner.path]
            : []
        if (recordingEffects && relevant) {
          events.push({
            phase: 'filesystem_operation_complete',
            monotonic_ns: process.hrtime.bigint().toString(),
            operation_id: operationId,
            operation: name,
            requested_ns: requestedNs,
            identity,
            attribution: requestedIdentity !== null
              ? 'async_context'
              : ownerIdentity !== null
                ? 'fd_owner'
                : 'missing',
            paths,
            success: error === null,
            error_code: error === null ? null : error.code || error.name || 'ERROR'
          })
        }
        if (name === 'close' && typeof fd === 'number') fdOwners.delete(fd)
        return callback.apply(this, callbackArgs)
      }
      return original.apply(this, args)
    }
  }
}

if (profile === 'effects') installEffectWrappers()

const tar = require(modulePath)
if (profile !== 'stock') {
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
    const identity = entryIdentity.get(entry) || null
    return entryContext.run(identity, () => originalCheckFs2.call(this, entry, error => {
      events.push({
        phase: 'entry_effect_complete',
        monotonic_ns: process.hrtime.bigint().toString(),
        identity,
        association_failure: identity === null ? 'entry was not observed by onReadEntry' : null,
        target_error: entryErrors.get(entry) || (error ? String(error) : null)
      })
      return fullyDone(error)
    }))
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
  let targetError = null
  recordingEffects = true
  try {
    await tar.x(options)
  } catch (error) {
    targetError = {
      name: error.name || 'Error',
      code: error.tarCode || error.code || 'WORKER_ERROR',
      message: String(error.message || error)
    }
  } finally {
    recordingEffects = false
  }
  const completed = process.hrtime.bigint()
  const finalSnapshot = snapshotTree(destination)
  const targetOutcome = targetError === null
    ? 'success'
    : typeof targetError.code === 'string' && targetError.code.startsWith('TAR_')
      ? 'rejected'
      : 'failed'
  process.stdout.write(JSON.stringify({
    schema_version: 1,
    profile,
    node_version: process.versions.node,
    tar_version: packageValue.version,
    unpack_sha256: actualUnpackSha256,
    package_entrypoint: entrypointPath,
    package_entrypoint_sha256: actualEntrypointSha256,
    target_duration_ns: Number(completed - started),
    target_outcome: targetOutcome,
    target_error: targetError,
    events,
    observation_failures: observationFailures,
    final_snapshot: finalSnapshot,
    final_semantic_snapshot: semanticSnapshot(finalSnapshot)
  }) + '\n')
  process.exitCode = targetOutcome === 'success' ? 0 : targetOutcome === 'rejected' ? 2 : 1
}

main().catch(error => {
  process.stderr.write(String(error.stack || error) + '\n')
  process.exitCode = 1
})
