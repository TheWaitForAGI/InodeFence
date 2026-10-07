// Benign qualification probe. This does not modify node-tar or extraction semantics.
'use strict'

const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

const [modulePath, archive, destination] = process.argv.slice(2)
if (!modulePath || !archive || !destination) {
  throw new Error('usage: entry-timing-probe.cjs MODULE ARCHIVE DESTINATION')
}

const tar = require(modulePath)
const events = []
let ordinal = 0

const observe = relative => {
  const absolute = path.join(destination, relative)
  try {
    const stat = fs.lstatSync(absolute)
    const kind = stat.isFile() ? 'regular' : stat.isDirectory() ? 'directory' :
      stat.isSymbolicLink() ? 'symlink' : 'other'
    return {
      exists: true,
      kind,
      size: stat.size,
      nlink: stat.nlink,
      mode: stat.mode & 0o7777,
      link_target: kind === 'symlink' ? fs.readlinkSync(absolute) : null,
      content_sha256: kind === 'regular' ?
        crypto.createHash('sha256').update(fs.readFileSync(absolute)).digest('hex') : null
    }
  } catch (error) {
    if (error.code === 'ENOENT') return {exists: false}
    throw error
  }
}

const main = async () => {
  await tar.x({
    file: archive,
    cwd: destination,
    strict: true,
    preservePaths: false,
    onReadEntry: entry => {
      const entryIndex = ordinal++
      const identity = {
        entry_index: entryIndex,
        path: entry.path,
        type: entry.type,
        linkpath: entry.linkpath || null
      }
      events.push({phase: 'on_read_entry', ...identity, observed: observe(entry.path)})
      entry.on('end', () => {
        events.push({phase: 'entry_end', ...identity, observed: observe(entry.path)})
      })
    }
  })

  events.push({
    phase: 'tar_x_resolved',
    observed: Object.fromEntries(
      ['regular', 'dir', 'hard', 'sym'].map(name => [name, observe(name)])
    )
  })
  process.stdout.write(JSON.stringify(events) + '\n')
}

main().catch(error => {
  process.stderr.write(String(error.stack || error) + '\n')
  process.exitCode = 1
})
