#!/usr/bin/env node

import { existsSync, readdirSync, rmSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const productsRoot = join(repoRoot, 'products')
const experimentsRoot = join(repoRoot, 'experiments')
const apply = process.argv.includes('--apply')
const check = process.argv.includes('--check')

const junkNames = new Set([
  '.DS_Store',
  '.env',
  '.knead-published.json',
  '.venv',
  '__pycache__',
  'outputs',
  'state.json',
  'versions',
])

function isJunk(path, entry) {
  if (junkNames.has(entry.name)) return true
  if (entry.name.endsWith('.pptx')) return true
  if (entry.name.endsWith('.lock')) return true
  if (entry.name.startsWith('hermes_intro.')) return true
  return false
}

function isRootJunk(entry) {
  if (entry.name === 'package-lock.json') return true
  if (entry.name.startsWith('.tmp-')) return true
  return false
}

function isExperimentJunk(entry) {
  if (['.next', '.vite', 'build', 'dist'].includes(entry.name)) return true
  if (entry.name.endsWith('.tsbuildinfo')) return true
  return false
}

function walk(dir, results) {
  if (!existsSync(dir)) return
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (isJunk(path, entry)) {
      results.push(path)
      continue
    }
    if (entry.isDirectory()) walk(path, results)
  }
}

function walkExperiments(dir, results) {
  if (!existsSync(dir)) return
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.name === 'generated' || isExperimentJunk(entry)) {
      results.push(path)
      continue
    }
    if (entry.isDirectory()) walkExperiments(path, results)
  }
}

const found = []
for (const entry of readdirSync(repoRoot, { withFileTypes: true })) {
  if (isRootJunk(entry)) {
    found.push(join(repoRoot, entry.name))
  }
}
walk(productsRoot, found)
walkExperiments(experimentsRoot, found)

if (!found.length) {
  console.log('No local release artifacts found.')
  process.exit(0)
}

console.log('Local release artifacts found:')
for (const path of found) {
  console.log(`- ${relative(repoRoot, path)}`)
}

if (check) {
  console.error('\nRun `pnpm release:clean:local -- --apply` to remove these local-only artifacts.')
  process.exit(1)
}

if (!apply) {
  console.log('\nDry run only. Run `pnpm release:clean:local -- --apply` to remove them.')
  process.exit(0)
}

for (const path of found) {
  rmSync(path, { recursive: true, force: true })
}
console.log(`Removed ${found.length} local release artifact${found.length === 1 ? '' : 's'}.`)
