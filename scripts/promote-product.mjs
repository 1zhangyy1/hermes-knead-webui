#!/usr/bin/env node

import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const args = process.argv.slice(2)
const apply = args.includes('--apply')
const force = args.includes('--force')
const candidateArg = args.find((arg) => !arg.startsWith('--'))

function usage() {
  console.error('Usage: pnpm product:promote -- <candidate-product-dir> [--apply] [--force]')
  console.error('')
  console.error('Dry run is the default. The candidate directory name must match product.json id.')
}

function fail(message) {
  console.error(message)
  process.exit(1)
}

function readJson(path, label) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch (error) {
    fail(`Could not read ${label}: ${error instanceof Error ? error.message : String(error)}`)
  }
}

function insertBeforeMarker(path, marker, line) {
  const current = readFileSync(path, 'utf8')
  if (current.includes(line)) return false
  if (!current.includes(marker)) {
    fail(`Could not update ${path}: marker was not found: ${marker}`)
  }
  writeFileSync(path, current.replace(marker, `${line}${marker}`), 'utf8')
  return true
}

function updateGitignore(productId) {
  const path = join(repoRoot, '.gitignore')
  return insertBeforeMarker(path, 'products/**/versions/\n', `!products/${productId}/\n!products/${productId}/**\n`)
}

function catalogEntryFromManifest(productId, manifest) {
  return {
    id: productId,
    title: manifest.title || productId,
    summary: manifest.desc || `Curated ${productId} example product.`,
  }
}

function sameCatalogEntry(left, right) {
  return left && left.id === right.id && left.title === right.title && left.summary === right.summary
}

function updateProductCatalog(productId, manifest) {
  const path = join(repoRoot, 'products', 'catalog.json')
  const catalog = readJson(path, 'products/catalog.json')
  const nextEntry = catalogEntryFromManifest(productId, manifest)
  catalog.builtins = Array.isArray(catalog.builtins) ? catalog.builtins : []
  const existingIndex = catalog.builtins.findIndex((item) => item && item.id === productId)
  if (existingIndex >= 0) {
    if (sameCatalogEntry(catalog.builtins[existingIndex], nextEntry)) return false
    catalog.builtins[existingIndex] = nextEntry
  } else {
    catalog.builtins.push(nextEntry)
  }
  writeFileSync(path, `${JSON.stringify(catalog, null, 2)}\n`, 'utf8')
  return true
}

if (!candidateArg) {
  usage()
  process.exit(1)
}

const candidateDir = resolve(candidateArg)
const productId = basename(candidateDir)
const destination = join(repoRoot, 'products', productId)

if (!existsSync(candidateDir)) {
  fail(`Candidate product directory does not exist: ${candidateArg}`)
}

const candidateManifest = readJson(join(candidateDir, 'product.json'), `${candidateArg}/product.json`)

const verify = spawnSync('node', ['scripts/verify-products.mjs', '--candidate', candidateDir], {
  cwd: repoRoot,
  encoding: 'utf8',
  stdio: ['ignore', 'pipe', 'pipe'],
})

if (verify.status !== 0) {
  if (verify.stdout) process.stdout.write(verify.stdout)
  if (verify.stderr) process.stderr.write(verify.stderr)
  fail('Candidate product failed validation; not promoting.')
}

if (existsSync(destination) && !force) {
  fail(`Destination already exists: ${relative(repoRoot, destination)}\nUse --force only when replacing a curated product intentionally.`)
}

console.log(`Candidate verified: ${relative(repoRoot, candidateDir)}`)
console.log(`Product id: ${productId}`)
console.log(`Destination: ${relative(repoRoot, destination)}`)
console.log('')
console.log('Planned changes:')
console.log(`- Copy candidate to ${relative(repoRoot, destination)}`)
console.log('- Add product allowlist entries to .gitignore')
console.log('- Add or update product entry in products/catalog.json')
console.log('')
console.log('After promotion, update README/docs if this product becomes part of the official MVP.')

if (!apply) {
  console.log('\nDry run only. Re-run with --apply to promote this product.')
  process.exit(0)
}

if (force && existsSync(destination)) {
  rmSync(destination, { recursive: true, force: true })
}
cpSync(candidateDir, destination, { recursive: true, errorOnExist: true })
const changed = [
  updateGitignore(productId),
  updateProductCatalog(productId, candidateManifest),
].filter(Boolean).length

console.log(`\nPromoted ${productId}. Updated ${changed} source allowlist file${changed === 1 ? '' : 's'}.`)
const postVerify = spawnSync('node', ['scripts/verify-products.mjs'], {
  cwd: repoRoot,
  encoding: 'utf8',
  stdio: ['ignore', 'pipe', 'pipe'],
})
if (postVerify.status !== 0) {
  if (postVerify.stdout) process.stdout.write(postVerify.stdout)
  if (postVerify.stderr) process.stderr.write(postVerify.stderr)
  fail('Promotion changed files, but built-in product verification failed. Fix the promoted product before committing.')
}
console.log('Built-in product verification passed. Run `pnpm verify` before committing.')
