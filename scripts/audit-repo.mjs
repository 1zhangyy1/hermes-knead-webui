#!/usr/bin/env node

import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'

const forbiddenTrackedPatterns = [
  [/^vendor\//, 'vendor reference checkouts are local-only'],
  [/^\.hermes-home\//, 'Hermes runtime state must stay outside Git'],
  [/^tmp\//, 'temporary output must stay outside Git'],
  [/^node_modules\//, 'dependencies must not be committed'],
  [/^\.tmp-/, 'local screenshots and scratch files must not be committed'],
  [/^products\/[^/]+\/versions\//, 'generated product versions are runtime output'],
  [/^experiments\/.*\/node_modules\//, 'experiment dependencies must not be committed'],
  [/^experiments\/.*\/dist\//, 'experiment builds must not be committed'],
  [/^experiments\/generated\//, 'generated experiment output must not be committed'],
  [/^apps\/webui\/\.github\//, 'only root .github workflows should exist in this repo'],
]

const requiredPaths = [
  'apps/webui/api/products.py',
  'apps/webui/static/product-runtime.js',
  'apps/webui/static/product-shell-runtime.js',
  'products/general/product.json',
  'products/ppt-designer/product.json',
  'docs/architecture/PRODUCTION_REPOSITORY_PLAN.md',
  '.github/workflows/verify.yml',
]

function gitLsFiles() {
  const result = spawnSync('git', ['ls-files'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  if (result.status !== 0) {
    throw new Error(result.stderr || 'git ls-files failed')
  }
  return result.stdout.split('\n').filter(Boolean)
}

let failed = false
const trackedFiles = gitLsFiles()

for (const file of trackedFiles) {
  for (const [pattern, reason] of forbiddenTrackedPatterns) {
    if (pattern.test(file)) {
      console.error(`FORBIDDEN tracked file: ${file}`)
      console.error(`  ${reason}`)
      failed = true
    }
  }
}

for (const requiredPath of requiredPaths) {
  if (!existsSync(requiredPath)) {
    console.error(`MISSING required path: ${requiredPath}`)
    failed = true
  }
}

if (failed) {
  process.exit(1)
}

console.log('Repository audit passed')
