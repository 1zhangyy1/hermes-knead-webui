#!/usr/bin/env node

import { spawnSync } from 'node:child_process'

const checkOnly = process.argv.includes('--check')
const jsonOutput = process.argv.includes('--json')
const stagingOutput = process.argv.includes('--staging')

const batchRules = [
  {
    name: 'release-foundation',
    description: 'Open-source metadata, CI, repository gates, setup scripts, and release tooling.',
    match: (path) =>
      [
        '.env.example',
        '.env.local.example',
        '.gitattributes',
        '.github/',
        '.gitignore',
        'CHANGELOG.md',
        'CODE_OF_CONDUCT.md',
        'CONTRIBUTING.md',
        'LICENSE',
        'NOTICE.md',
        'README.md',
        'RELEASE.md',
        'SECURITY.md',
        'package.json',
        'pnpm-lock.yaml',
      ].some((prefix) => path === prefix || path.startsWith(prefix)) ||
      /^scripts\/(?:audit-repo|check-markdown-links|check-source-whitespace|clean-local-artifacts|dev-webui|hermes-local|promote-product|release-batches|release-check|scan-secrets|setup-local|verify|verify-product-core|verify-products|webui-smoke)\.(?:mjs|py|sh)$/.test(path),
  },
  {
    name: 'product-model-docs',
    description: 'Product definition, UI/UX contract, architecture notes, and archive/experiment boundaries.',
    match: (path) =>
      path === 'PRODUCT.md' ||
      path === 'PRODUCT_UIUX.md' ||
      path === 'DESIGN.md' ||
      path.startsWith('experiments/') ||
      path.startsWith('docs/'),
  },
  {
    name: 'webui-product-runtime',
    description: 'WebUI product runtime, creation/shape flow, API glue, and product-layer tests.',
    match: (path) => path.startsWith('apps/webui/'),
  },
  {
    name: 'curated-products',
    description: 'Source-owned built-in product examples and product manifest schemas.',
    match: (path) => path.startsWith('products/'),
  },
  {
    name: 'runtime-vendoring',
    description: 'Bundled Hermes runtime policy, upstream metadata, and local patch notes.',
    match: (path) => path.startsWith('runtimes/'),
  },
  {
    name: 'agent-skills',
    description: 'Repository-local agent skills used to shape Knead products.',
    match: (path) => path.startsWith('.agents/skills/'),
  },
]

const batchDependencies = {
  'release-foundation': [
    'product-model-docs',
    'webui-product-runtime',
    'curated-products',
    'runtime-vendoring',
  ],
  'webui-product-runtime': ['curated-products'],
}

const reviewGuidance = [
  {
    name: 'release-surface',
    batches: ['release-foundation', 'product-model-docs', 'curated-products', 'runtime-vendoring'],
    note: 'Review together when checking docs, notices, product source boundaries, and release gates.',
  },
  {
    name: 'runtime-implementation',
    batches: ['webui-product-runtime'],
    note: 'Review after product source boundaries are understood; product tests depend on curated products.',
  },
  {
    name: 'agent-skills',
    batches: ['agent-skills'],
    note: 'Review independently as local instructions used by product-shaping agents.',
  },
]

function gitStatusLines() {
  const result = spawnSync('git', ['status', '--porcelain=v1', '--untracked-files=all'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  if (result.status !== 0) {
    throw new Error(result.stderr || 'git status failed')
  }
  return result.stdout.split('\n').filter(Boolean)
}

function parseStatusLine(line) {
  const status = line.slice(0, 2)
  let path = line.slice(3).replace(/^"|"$/g, '')
  if (path.includes(' -> ')) {
    path = path.split(' -> ').pop()
  }
  return { status, path }
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, "'\\''")}'`
}

const batches = new Map(batchRules.map((rule) => [rule.name, []]))
const unknown = []

for (const item of gitStatusLines().map(parseStatusLine)) {
  const rule = batchRules.find((candidate) => candidate.match(item.path))
  if (!rule) {
    unknown.push(item)
    continue
  }
  batches.get(rule.name).push(item)
}

const changedCount = [...batches.values()].reduce((sum, files) => sum + files.length, 0) + unknown.length
const result = {
  changedCount,
  batches: batchRules.map((rule) => ({
    name: rule.name,
    description: rule.description,
    dependencies: batchDependencies[rule.name] || [],
    files: batches.get(rule.name),
  })),
  reviewGuidance,
  unknown,
}

if (jsonOutput) {
  console.log(JSON.stringify(result, null, 2))
}

if (stagingOutput) {
  console.log('Release batch staging commands')
  console.log('Review each batch before running the corresponding git command.\n')
  for (const rule of batchRules) {
    const files = batches.get(rule.name)
    if (!files.length) continue
    console.log(`# ${rule.name}: ${rule.description}`)
    console.log(`git add -- ${files.map((file) => shellQuote(file.path)).join(' ')}`)
    console.log('')
  }
}

if (!checkOnly && !jsonOutput && !stagingOutput) {
  console.log('Release batch plan')
  console.log('Use this as a non-destructive guide for staging reviewable commits.\n')

  for (const rule of batchRules) {
    const files = batches.get(rule.name)
    if (!files.length) continue
    console.log(`${rule.name} (${files.length})`)
    console.log(`  ${rule.description}`)
    for (const file of files) {
      console.log(`  ${file.status} ${file.path}`)
    }
    console.log('')
  }

  console.log('Review guidance')
  for (const group of reviewGuidance) {
    const activeBatches = group.batches.filter((name) => batches.get(name)?.length)
    if (!activeBatches.length) continue
    console.log(`  ${group.name}: ${activeBatches.join(', ')}`)
    console.log(`    ${group.note}`)
  }
  console.log('')

  console.log('Batch dependencies')
  for (const rule of batchRules) {
    const files = batches.get(rule.name)
    const dependencies = batchDependencies[rule.name] || []
    if (!files.length || !dependencies.length) continue
    console.log(`  ${rule.name} depends on ${dependencies.join(', ')}`)
  }
  console.log('')
}

if (unknown.length) {
  console.error('Unclassified changes:')
  for (const file of unknown) {
    console.error(`  ${file.status} ${file.path}`)
  }
  console.error('\nUpdate scripts/release-batches.mjs before preparing release commits.')
  process.exit(1)
}

if (checkOnly) {
  const nonEmptyBatchCount = [...batches.values()].filter((files) => files.length).length
  console.log(`Release batch classification check passed (${changedCount} change${changedCount === 1 ? '' : 's'} across ${nonEmptyBatchCount} batch${nonEmptyBatchCount === 1 ? '' : 'es'}).`)
} else if (!jsonOutput && !stagingOutput && !changedCount) {
  console.log('No local changes.')
}
