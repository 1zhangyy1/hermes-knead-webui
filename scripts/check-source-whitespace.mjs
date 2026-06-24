#!/usr/bin/env node

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, statSync } from 'node:fs'

const maxFileBytes = 2 * 1024 * 1024
const binaryExtensions = new Set([
  '.avif',
  '.gif',
  '.ico',
  '.jpg',
  '.jpeg',
  '.pdf',
  '.png',
  '.ppt',
  '.pptx',
  '.webp',
  '.woff',
  '.woff2',
  '.zip',
])

const ignoredPathPrefixes = [
  '.git/',
  '.hermes-home/',
  '.agents/skills/impeccable/',
  '.agents/skills/doc/',
  '.agents/skills/browser/',
  'apps/webui/tests/',
  'docs/archive/',
  'node_modules/',
  'runtimes/hermes-agent/',
  'vendor/',
]

const ignoredPathSegments = [
  '/node_modules/',
  '/__pycache__/',
  '/.pytest_cache/',
  '/.venv/',
  '/.venv311/',
]

const rootReleaseFiles = new Set([
  '.env.example',
  '.gitattributes',
  '.gitignore',
  'CHANGELOG.md',
  'CODE_OF_CONDUCT.md',
  'CONTRIBUTING.md',
  'LICENSE',
  'NOTICE.md',
  'PRODUCT.md',
  'PRODUCT_UIUX.md',
  'README.md',
  'RELEASE.md',
  'SECURITY.md',
  'package.json',
  'pnpm-lock.yaml',
  'pnpm-workspace.yaml',
  'apps/webui/README.md',
  'apps/webui/requirements-dev.txt',
  'apps/webui/requirements.txt',
  'runtimes/README.md',
])

const releaseOwnedPrefixes = [
  '.github/',
  '.agents/skills/knead-product/',
  'apps/webui/api/',
  'apps/webui/static/',
  'docs/',
  'packages/',
  'products/',
  'scripts/',
]

const releaseOwnedTestFiles = new Set([
  'apps/webui/tests/test_streaming_runtime_prompt.py',
])

function gitCandidateFiles() {
  const result = spawnSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  if (result.status !== 0) {
    throw new Error(result.stderr || 'git ls-files failed')
  }
  return result.stdout.split('\n').filter(Boolean)
}

function isReleaseOwnedTestPath(path) {
  return releaseOwnedTestFiles.has(path) || /^apps\/webui\/tests\/test_product_[^/]+\.py$/.test(path)
}

function shouldSkipPath(path) {
  if (isReleaseOwnedTestPath(path)) return false
  if (ignoredPathPrefixes.some((prefix) => path.startsWith(prefix))) return true
  if (ignoredPathSegments.some((segment) => path.includes(segment))) return true
  const lower = path.toLowerCase()
  for (const ext of binaryExtensions) {
    if (lower.endsWith(ext)) return true
  }
  return false
}

function isReleaseOwnedPath(path) {
  return (
    rootReleaseFiles.has(path) ||
    isReleaseOwnedTestPath(path) ||
    releaseOwnedPrefixes.some((prefix) => path.startsWith(prefix))
  )
}

let failed = false

for (const file of gitCandidateFiles()) {
  if (!isReleaseOwnedPath(file)) continue
  if (shouldSkipPath(file) || !existsSync(file)) continue
  const stat = statSync(file)
  if (!stat.isFile() || stat.size > maxFileBytes) continue
  const buffer = readFileSync(file)
  if (buffer.includes(0)) continue

  const text = buffer.toString('utf8')
  const lines = text.split('\n')
  for (const [index, rawLine] of lines.entries()) {
    const lineNumber = index + 1
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine

    if (/[ \t]+$/.test(line)) {
      console.error(`TRAILING WHITESPACE: ${file}:${lineNumber}`)
      failed = true
    }
    if (/^(<<<<<<<|=======|>>>>>>>)($|[ \t])/.test(line)) {
      console.error(`CONFLICT MARKER: ${file}:${lineNumber}`)
      failed = true
    }
  }
}

if (failed) {
  process.exit(1)
}

console.log('Source whitespace check passed')
