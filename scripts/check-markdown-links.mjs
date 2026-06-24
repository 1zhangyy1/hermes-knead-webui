#!/usr/bin/env node

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, normalize } from 'node:path'

const rootMarkdownFiles = new Set([
  'CHANGELOG.md',
  'CODE_OF_CONDUCT.md',
  'CONTRIBUTING.md',
  'DESIGN.md',
  'NOTICE.md',
  'PRODUCT.md',
  'PRODUCT_UIUX.md',
  'README.md',
  'RELEASE.md',
  'SECURITY.md',
])

const releaseMarkdownPrefixes = [
  '.agents/skills/knead-product/',
  '.github/',
  'docs/architecture/',
  'docs/references/',
  'docs/research/',
  'products/',
]

const releaseMarkdownFiles = new Set([
  'docs/README.md',
  'docs/PRODUCT_MODEL_CONTRACT.md',
  'apps/webui/AGENTS.md',
  'apps/webui/CONTRIBUTING.md',
  'apps/webui/README.md',
  'experiments/README.md',
  'runtimes/README.md',
])

const ignoredPrefixes = [
  '.git/',
  '.hermes-home/',
  '.agents/skills/impeccable/',
  'apps/webui/.venv/',
  'apps/webui/.venv311/',
  'apps/webui/.pytest_cache/',
  'docs/archive/',
  'node_modules/',
  'runtimes/hermes-agent/',
  'vendor/',
]

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

function isIgnored(path) {
  return ignoredPrefixes.some((prefix) => path.startsWith(prefix))
}

function isReleaseMarkdown(path) {
  if (!path.endsWith('.md') || isIgnored(path)) return false
  return (
    rootMarkdownFiles.has(path) ||
    releaseMarkdownFiles.has(path) ||
    releaseMarkdownPrefixes.some((prefix) => path.startsWith(prefix))
  )
}

function normalizeTarget(rawTarget) {
  let target = rawTarget.trim()
  if (!target || target.startsWith('#')) return null
  if (/^(?:https?:|mailto:|tel:)/i.test(target)) return null
  if (target.startsWith('<') && target.endsWith('>')) {
    target = target.slice(1, -1)
  }
  target = target.split('#')[0].split('?')[0].trim()
  if (!target) return null
  try {
    target = decodeURIComponent(target)
  } catch {
    // Keep the raw target if it is not valid percent-encoded text.
  }
  return target
}

function resolveTarget(sourceFile, target) {
  if (target.startsWith('/')) {
    return normalize(target.slice(1))
  }
  return normalize(join(dirname(sourceFile), target))
}

let failed = false

for (const file of gitCandidateFiles().filter(isReleaseMarkdown)) {
  if (!existsSync(file) || !statSync(file).isFile()) continue
  const text = readFileSync(file, 'utf8')
  const linkPattern = /!?\[[^\]]*]\(([^)\n]+)\)/g
  for (const match of text.matchAll(linkPattern)) {
    const target = normalizeTarget(match[1])
    if (!target) continue
    const resolved = resolveTarget(file, target)
    if (resolved.startsWith('..')) {
      console.error(`BROKEN MARKDOWN LINK: ${file}`)
      console.error(`  ${match[1]} resolves outside the repository`)
      failed = true
      continue
    }
    if (!existsSync(resolved)) {
      console.error(`BROKEN MARKDOWN LINK: ${file}`)
      console.error(`  ${match[1]} -> ${resolved}`)
      failed = true
    }
  }
}

if (failed) {
  process.exit(1)
}

console.log('Markdown link check passed')
