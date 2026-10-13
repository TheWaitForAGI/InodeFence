// Bounded entry-associated filesystem-effect producer for pinned node-tar.
'use strict'

const {AsyncLocalStorage} = require('node:async_hooks')
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

const PROTOCOL_ID = 'inodefence-node-tar-effect-stream'
const PROTOCOL_VERSION = '2.0.0'
const SOURCE_ID = 'node-tar-effect-worker-v2'
const MAX_EVENT_BOUND = 256
const MAX_FRAME_BYTES = 900 * 1024

const sha256 = value => crypto.createHash('sha256').update(value).digest('hex')
const digestFile = filename => sha256(fs.readFileSync(filename))

const stableStringify = value => {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (value !== null && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(key =>
      `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

const moduleIdentity = (modulePath, lockPath) => {
  const packagePath = path.join(modulePath, 'package.json')
  const unpackPath = path.join(modulePath, 'dist/commonjs/unpack.js')
  const entrypointPath = require.resolve(modulePath)
  const packageValue = JSON.parse(fs.readFileSync(packagePath, 'utf8'))
  if (packageValue.name !== 'tar') throw new Error('Expected the node-tar package')
  return {
    node_version: process.versions.node,
    tar_version: packageValue.version,
    producer_sha256: digestFile(__filename),
    package_lock_sha256: digestFile(lockPath),
    package_entrypoint: entrypointPath,
    package_entrypoint_sha256: digestFile(entrypointPath),
    unpack_sha256: digestFile(unpackPath)
  }
}

const identify = args => {
  if (args.length !== 2) {
    throw new Error('usage: effect-producer.cjs --identify MODULE LOCK')
  }
  process.stdout.write(JSON.stringify(moduleIdentity(args[0], args[1])))
}

const symbolsByDescription = (prototype, description) =>
  Object.getOwnPropertySymbols(prototype).filter(symbol => symbol.description === description)

const statVersion = stat => [
  stat.dev, stat.ino, stat.mode, stat.nlink, stat.uid, stat.gid,
  stat.size, stat.mtimeNs, stat.ctimeNs
].map(value => value.toString())

const sameVersion = (left, right) =>
  left.length === right.length && left.every((value, index) => value === right[index])

const objectKind = stat => stat.isFile()
  ? 'regular'
  : stat.isDirectory()
    ? 'directory'
    : stat.isSymbolicLink()
      ? 'symlink'
      : 'other'

const digestRegular = (absolute, expected) => {
  const flags = fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW |
    fs.constants.O_NONBLOCK | fs.constants.O_CLOEXEC
  const descriptor = fs.openSync(absolute, flags)
  try {
    const opened = fs.fstatSync(descriptor, {bigint: true})
    if (!opened.isFile() || opened.dev !== expected.dev || opened.ino !== expected.ino) {
      throw new Error('object identity changed while opening for digest')
    }
    const hash = crypto.createHash('sha256')
    const buffer = Buffer.allocUnsafe(64 * 1024)
    let offset = 0
    while (true) {
      const count = fs.readSync(descriptor, buffer, 0, buffer.length, offset)
      if (count === 0) break
      hash.update(buffer.subarray(0, count))
      offset += count
    }
    const final = fs.fstatSync(descriptor, {bigint: true})
    if (!sameVersion(statVersion(opened), statVersion(final))) {
      throw new Error('object changed while reading digest')
    }
    return hash.digest('hex')
  } finally {
    fs.closeSync(descriptor)
  }
}

const captureObject = (sandboxRoot, relative) => {
  const absolute = relative === '.' ? sandboxRoot : path.join(sandboxRoot, relative)
  try {
    const before = fs.lstatSync(absolute, {bigint: true})
    const kind = objectKind(before)
    const content = kind === 'regular' ? digestRegular(absolute, before) : null
    const linkTarget = kind === 'symlink' ? fs.readlinkSync(absolute) : null
    const after = fs.lstatSync(absolute, {bigint: true})
    if (!sameVersion(statVersion(before), statVersion(after))) {
      throw new Error('object changed during effect observation')
    }
    return {
      status: 'present',
      object: {
        path: relative,
        object_type: kind,
        st_dev: before.dev.toString(),
        st_ino: before.ino.toString(),
        st_nlink: before.nlink.toString(),
        mode: Number(before.mode & 0o7777n),
        size: before.size.toString(),
        uid: before.uid.toString(),
        gid: before.gid.toString(),
        mtime_ns: before.mtimeNs.toString(),
        ctime_ns: before.ctimeNs.toString(),
        symlink_target: linkTarget,
        content_digest: content
      },
      error: null
    }
  } catch (error) {
    if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) {
      return {status: 'absent', object: null, error: null}
    }
    return {
      status: 'not_observed',
      object: null,
      error: {
        code: error && (error.code || error.name) || 'OBSERVATION_ERROR',
        message: String(error && error.message || error)
      }
    }
  }
}

const run = async args => {
  if (args.length !== 12) {
    throw new Error(
      'usage: effect-producer.cjs MODULE LOCK ARCHIVE DESTINATION minimal|full ' +
      'EVENT_BOUND EXPECTED_NODE EXPECTED_TAR EXPECTED_PRODUCER_SHA256 ' +
      'EXPECTED_LOCK_SHA256 EXPECTED_ENTRYPOINT_SHA256 EXPECTED_UNPACK_SHA256'
    )
  }
  const [
    modulePath, lockPath, archive, destination, profile, eventBoundText,
    expectedNode, expectedTar, expectedProducerSha256, expectedLockSha256,
    expectedEntrypointSha256, expectedUnpackSha256
  ] = args
  if (!new Set(['minimal', 'full']).has(profile)) throw new Error('invalid effect profile')
  const eventBound = Number(eventBoundText)
  if (!Number.isInteger(eventBound) || eventBound < 1 || eventBound > MAX_EVENT_BOUND) {
    throw new Error(`event bound must be in 1..${MAX_EVENT_BOUND}`)
  }
  const identity = moduleIdentity(modulePath, lockPath)
  const expected = {
    node_version: expectedNode,
    tar_version: expectedTar,
    producer_sha256: expectedProducerSha256,
    package_lock_sha256: expectedLockSha256,
    package_entrypoint_sha256: expectedEntrypointSha256,
    unpack_sha256: expectedUnpackSha256
  }
  for (const [field, value] of Object.entries(expected)) {
    if (identity[field] !== value) {
      const error = new Error(`Target identity changed: ${field}`)
      error.code = 'VERSION_MISMATCH'
      throw error
    }
  }

  const sandboxRoot = path.dirname(path.resolve(destination))
  const normalizedPath = value => {
    if (typeof value === 'string' || Buffer.isBuffer(value)) return path.resolve(String(value))
    if (value instanceof URL && value.protocol === 'file:') return path.resolve(value.pathname)
    return null
  }
  const sandboxRelative = value => {
    const normalized = normalizedPath(value)
    if (normalized === null || (normalized !== sandboxRoot &&
        !normalized.startsWith(`${sandboxRoot}${path.sep}`))) return null
    return path.relative(sandboxRoot, normalized).split(path.sep).join('/') || '.'
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
  const effectCoverage = {
    namespace_creation: 'supported_when_one correlated operation proves absent-to-present',
    namespace_removal: 'supported_when_one correlated operation proves present-to-absent',
    namespace_replacement: 'supported_when one correlated operation changes identity or type',
    regular_file_content_modification: 'supported by stable before/after content digests',
    truncation: 'supported by stable before/after regular-file sizes',
    metadata_modification: 'supported by stable before/after metadata fields',
    symlink_creation: 'supported by absent-to-symlink evidence and raw link text',
    hardlink_identity_relation_creation: 'supported by source/destination lstat identity evidence',
    identity_relation_removal: 'unsupported: no counterpart provenance for single-path removal'
  }
  const coverage = {
    lifecycle_kinds: ['read', 'effect_work_started', 'effect_work_settled'],
    operation_callbacks: profile === 'full' ? Object.keys(operationSpecs) : [],
    effect_classes: effectCoverage,
    path_scope: 'sandbox-relative callback paths and proven descriptor-owner paths',
    observation_perturbation: profile === 'full'
      ? 'synchronous lstat/content probes at callback request and completion boundaries'
      : 'entry lifecycle and async-context propagation only'
  }

  const records = []
  let nextSequence = 0
  let droppedRecords = 0
  let overflow = false
  const emit = value => {
    const sequence = nextSequence++
    if (records.length >= eventBound) {
      overflow = true
      droppedRecords += 1
      return null
    }
    records.push({sequence, source_id: SOURCE_ID, ...value})
    return sequence
  }
  const instant = () => {
    const value = process.hrtime.bigint().toString()
    return {started_ns: value, finished_ns: value}
  }
  const observePaths = paths => {
    const started = process.hrtime.bigint().toString()
    const observations = paths.map(relative => ({
      path: relative,
      observation: captureObject(sandboxRoot, relative)
    }))
    return {
      interval: {started_ns: started, finished_ns: process.hrtime.bigint().toString()},
      observations
    }
  }
  const entryContext = new AsyncLocalStorage()
  const entryIdentity = new WeakMap()
  const entryErrors = new WeakMap()
  const fdOwners = new Map()
  let ordinal = 0
  let operationOrdinal = 0
  let recording = false

  const sameEntry = (left, right) => left !== null && right !== null &&
    left.ordinal === right.ordinal && left.path === right.path &&
    left.type === right.type && left.link_target === right.link_target

  const installEffectWrappers = () => {
    for (const [name, spec] of Object.entries(operationSpecs)) {
      const original = fs[name]
      if (typeof original !== 'function') continue
      fs[name] = function (...callArgs) {
        const callbackIndex = callArgs.findLastIndex(value => typeof value === 'function')
        if (callbackIndex === -1 || !recording) return original.apply(this, callArgs)
        const context = entryContext.getStore() || null
        const requestedPaths = spec.pathIndexes
          .map(index => sandboxRelative(callArgs[index]))
          .filter(value => value !== null)
        const fd = spec.fdIndex === null ? null : callArgs[spec.fdIndex]
        const owner = typeof fd === 'number' ? fdOwners.get(fd) || null : null
        const ownerPath = owner === null ? null : owner.path
        const paths = requestedPaths.length > 0
          ? requestedPaths
          : ownerPath === null
            ? []
            : [ownerPath]
        if (context === null && owner === null && paths.length === 0) {
          return original.apply(this, callArgs)
        }
        const contextEntry = context === null ? null : context.entry
        const ownerEntry = owner === null ? null : owner.entry
        const conflict = contextEntry !== null && ownerEntry !== null &&
          !sameEntry(contextEntry, ownerEntry)
        const entry = contextEntry || ownerEntry
        const association = contextEntry !== null
          ? 'async_context'
          : ownerEntry !== null
            ? 'handle_provenance'
            : 'missing'
        const before = observePaths(paths)
        const correlationId = `operation-${operationOrdinal++}`
        const startSequence = emit({
          record_type: 'operation_start',
          record_id: `${correlationId}-start`,
          correlation_id: correlationId,
          operation: name,
          entry,
          association,
          association_conflict: conflict,
          context_start_sequence: context === null ? null : context.work_start_sequence,
          handle_origin_completion_sequence: owner === null
            ? null
            : owner.origin_completion_sequence,
          paths,
          observation: before.interval,
          object_observations: before.observations,
          detail: {
            symlink_target: name === 'symlink' ? String(callArgs[0]) : null,
            open_flags: name === 'open' && (typeof callArgs[1] === 'string' ||
              typeof callArgs[1] === 'number') ? String(callArgs[1]) : null
          }
        })
        const callback = callArgs[callbackIndex]
        let completed = false
        const complete = (error, callbackArgs) => {
          if (completed) return null
          completed = true
          const after = observePaths(paths)
          const completionSequence = emit({
            record_type: 'operation_completion',
            record_id: `${correlationId}-completion`,
            correlation_id: correlationId,
            operation: name,
            entry,
            association,
            association_conflict: conflict,
            start_sequence: startSequence,
            paths,
            observation: after.interval,
            object_observations: after.observations,
            success: error === null,
            error_code: error === null ? null : error.code || error.name || 'ERROR',
            error_message: error === null ? null : String(error.message || error)
          })
          if (name === 'open' && error === null && typeof callbackArgs[1] === 'number' &&
              entry !== null && paths.length === 1 && completionSequence !== null) {
            fdOwners.set(callbackArgs[1], {
              entry,
              path: paths[0],
              origin_completion_sequence: completionSequence
            })
          }
          if (name === 'close' && typeof fd === 'number') fdOwners.delete(fd)
          return completionSequence
        }
        callArgs[callbackIndex] = function (...callbackArgs) {
          complete(callbackArgs[0] || null, callbackArgs)
          return callback.apply(this, callbackArgs)
        }
        try {
          return original.apply(this, callArgs)
        } catch (error) {
          complete(error, [error])
          throw error
        }
      }
    }
  }

  if (profile === 'full') installEffectWrappers()
  const tar = require(modulePath)
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
    entryErrors.set(entry, {
      code: error.tarCode || error.code || error.name || 'ERROR',
      message: String(error.message || error)
    })
    return originalOnError.call(this, error, entry)
  }
  Unpack.prototype[checkFs2] = function (entry, fullyDone) {
    const identityValue = entryIdentity.get(entry) || null
    const workStartSequence = emit({
      record_type: 'lifecycle',
      record_id: `entry-${identityValue === null ? 'missing' : identityValue.ordinal}-work-start`,
      entry: identityValue,
      kind: 'effect_work_started',
      observation: instant(),
      success: identityValue !== null,
      error: identityValue === null ? 'entry was not observed by onReadEntry' : null
    })
    const context = {entry: identityValue, work_start_sequence: workStartSequence}
    return entryContext.run(context, () => originalCheckFs2.call(this, entry, error => {
      const targetError = entryErrors.get(entry) || (error
        ? {code: error.code || error.name || 'ERROR', message: String(error.message || error)}
        : null)
      emit({
        record_type: 'lifecycle',
        record_id: `entry-${identityValue === null ? 'missing' : identityValue.ordinal}-work-settled`,
        entry: identityValue,
        kind: 'effect_work_settled',
        observation: instant(),
        success: targetError === null && identityValue !== null,
        error: targetError
      })
      return fullyDone(error)
    }))
  }

  const options = {
    file: archive,
    cwd: destination,
    strict: true,
    preservePaths: false,
    onReadEntry: entry => {
      const entryValue = {
        ordinal: ordinal++,
        path: entry.path,
        type: entry.type,
        link_target: entry.linkpath || null
      }
      entryIdentity.set(entry, entryValue)
      emit({
        record_type: 'lifecycle',
        record_id: `entry-${entryValue.ordinal}-read`,
        entry: entryValue,
        kind: 'read',
        observation: instant(),
        success: true,
        error: null
      })
    }
  }

  let targetError = null
  const startedNs = process.hrtime.bigint()
  recording = true
  try {
    await tar.x(options)
  } catch (error) {
    targetError = {
      name: error.name || 'Error',
      code: error.tarCode || error.code || 'WORKER_ERROR',
      message: String(error.message || error)
    }
  } finally {
    recording = false
  }
  const completedNs = process.hrtime.bigint()
  const targetOutcome = targetError === null
    ? 'success'
    : typeof targetError.code === 'string' && targetError.code.startsWith('TAR_')
      ? 'rejected'
      : 'failed'
  if (targetError !== null) process.stderr.write(JSON.stringify(targetError) + '\n')

  const producerFailures = []
  if (fdOwners.size !== 0) producerFailures.push({
    kind: 'unclosed_handle_provenance', count: fdOwners.size
  })
  const source = {
    source_id: SOURCE_ID,
    protocol_id: PROTOCOL_ID,
    protocol_version: PROTOCOL_VERSION,
    ...identity
  }
  const makeEnvelope = (framedRecords, extraDropped, frameOverflow) => {
    const recordsCanonical = stableStringify(framedRecords)
    return {
      format: PROTOCOL_ID,
      schema_version: 1,
      profile,
      event_bound: eventBound,
      source,
      input: {archive_sha256: digestFile(archive)},
      coverage,
      target: {
        outcome: targetOutcome,
        error: targetError,
        duration_ns: (completedNs - startedNs).toString()
      },
      records: framedRecords,
      terminal: {
        record_count: framedRecords.length,
        last_produced_sequence: framedRecords.length === 0
          ? -1
          : framedRecords[framedRecords.length - 1].sequence,
        last_attempted_sequence: nextSequence - 1,
        records_sha256: sha256(Buffer.from(recordsCanonical, 'utf8')),
        overflow: overflow || frameOverflow,
        dropped_records: droppedRecords + extraDropped,
        producer_failures: producerFailures,
        flush: 'synchronous_stdout_write'
      }
    }
  }
  let framedRecords = records
  let extraDropped = 0
  let envelope = makeEnvelope(framedRecords, extraDropped, false)
  let encoded = Buffer.from(JSON.stringify(envelope) + '\n', 'utf8')
  while (encoded.length > MAX_FRAME_BYTES && framedRecords.length > 0) {
    framedRecords = framedRecords.slice(0, -1)
    extraDropped += 1
    envelope = makeEnvelope(framedRecords, extraDropped, true)
    encoded = Buffer.from(JSON.stringify(envelope) + '\n', 'utf8')
  }
  if (encoded.length > MAX_FRAME_BYTES) throw new Error('terminal effect frame exceeds bound')
  let written = 0
  while (written < encoded.length) written += fs.writeSync(1, encoded, written)
  process.exitCode = targetOutcome === 'success' ? 0 : targetOutcome === 'rejected' ? 2 : 1
}

const main = async () => {
  const args = process.argv.slice(2)
  if (args[0] === '--identify') return identify(args.slice(1))
  return run(args)
}

main().catch(error => {
  const code = error.tarCode || error.code || 'WORKER_ERROR'
  process.stderr.write(JSON.stringify({code, message: String(error.message || error)}) + '\n')
  process.exitCode = code === 'VERSION_MISMATCH' ? 3 :
    typeof code === 'string' && code.startsWith('TAR_') ? 2 : 1
})
