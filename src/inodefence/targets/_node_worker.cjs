// Harness diagnostics stay in pipes; no bookkeeping within the snapshot window.
'use strict'
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')

async function main() {
  const args = process.argv.slice(2)
  if (args[0] === '--identify') {
    const pkg = JSON.parse(fs.readFileSync(path.join(args[1], 'package.json'), 'utf8'))
    if (pkg.name !== 'tar') throw new Error('Expected the node-tar package')
    const digest = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
    const metadata = {
      node_version: process.versions.node, tar_version: pkg.version,
      worker_sha256: digest(__filename)
    }
    if (args[2]) {
      metadata.package_lock_sha256 = digest(args[2])
      metadata.unavailable_tools = ['sh', 'npm', 'git', 'ssh', 'curl', 'gcc'].filter(
        name => !['/bin', '/usr/bin', '/usr/local/bin'].some(dir => fs.existsSync(path.join(dir, name)))
      )
    }
    process.stdout.write(JSON.stringify(metadata))
    return
  }
  const [modulePath, archive, destination, expectedNode, expectedTar] = args
  const pkg = JSON.parse(fs.readFileSync(path.join(modulePath, 'package.json'), 'utf8'))
  if (process.versions.node !== expectedNode || pkg.version !== expectedTar || pkg.name !== 'tar') {
    const error = new Error('Target identity changed after setup')
    error.code = 'VERSION_MISMATCH'
    throw error
  }
  const tar = require(modulePath)
  await tar.x({file: archive, cwd: destination, strict: true, preservePaths: false})
}

main().catch(error => {
  const code = error.tarCode || error.code || 'WORKER_ERROR'
  process.stderr.write(JSON.stringify({code, message: String(error.message)}) + '\n')
  process.exitCode = code === 'VERSION_MISMATCH' ? 3 :
    typeof code === 'string' && code.startsWith('TAR_') ? 2 : 1
})
