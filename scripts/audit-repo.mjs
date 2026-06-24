#!/usr/bin/env node

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'

const forbiddenTrackedPatterns = [
  [/^vendor\//, 'vendor reference checkouts are local-only'],
  [/^\.hermes-home\//, 'Hermes runtime state must stay outside Git'],
  [/^tmp\//, 'temporary output must stay outside Git'],
  [/^node_modules\//, 'dependencies must not be committed'],
  [/^package-lock\.json$/, 'this workspace uses pnpm; do not commit npm lockfiles'],
  [/^\.tmp-/, 'local screenshots and scratch files must not be committed'],
  [/^products\/[^/]+\/versions\//, 'generated product versions are runtime output'],
  [/^products\/.*\/outputs\//, 'generated product outputs are runtime output'],
  [/^products\/.*\/\.env$/, 'product secrets must stay local; commit .env.example only'],
  [/^products\/.*\/\.knead-published\.json$/, 'published draft markers are runtime state, not curated product source'],
  [/^products\/.*\/\.DS_Store$/, 'macOS metadata files must not be committed'],
  [/^products\/.*\/state\.json$/, 'product runtime state must stay outside Git'],
  [/^products\/.*\.pptx$/, 'exported decks are product output, not curated source'],
  [/^products\/.*\.lock$/, 'generated product lockfiles are runtime output'],
  [/^experiments\/.*\/node_modules\//, 'experiment dependencies must not be committed'],
  [/^experiments\/.*\/dist\//, 'experiment builds must not be committed'],
  [/^experiments\/generated\//, 'generated experiment output must not be committed'],
  [/^apps\/webui\/\.github\//, 'only root .github workflows should exist in this repo'],
]

const staticAllowedProductRoots = new Set([
  'README.md',
  'catalog.json',
  'product-catalog.schema.json',
  'product.schema.json',
])

const allowedDocsRootEntries = new Set([
  'README.md',
  'PRODUCT_MODEL_CONTRACT.md',
  'architecture',
  'archive',
  'brand',
  'references',
  'research',
])

const requiredPaths = [
  'README.md',
  'NOTICE.md',
  'DESIGN.md',
  'CHANGELOG.md',
  'RELEASE.md',
  'CONTRIBUTING.md',
  'CODE_OF_CONDUCT.md',
  'SECURITY.md',
  'package.json',
  'pnpm-lock.yaml',
  'pnpm-workspace.yaml',
  '.gitignore',
  '.gitattributes',
  'apps/webui/api/products.py',
  'apps/webui/static/product-runtime.js',
  'apps/webui/static/product-shell-runtime.js',
  'apps/webui/AGENTS.md',
  'apps/webui/CONTRIBUTING.md',
  'apps/webui/README.md',
  'scripts/verify-product-core.py',
  'scripts/verify-products.mjs',
  'scripts/check-source-whitespace.mjs',
  'scripts/check-markdown-links.mjs',
  'scripts/webui-smoke.mjs',
  'scripts/clean-local-artifacts.mjs',
  'scripts/setup-local.sh',
  'scripts/hermes-local.sh',
  'scripts/release-batches.mjs',
  'scripts/release-check.mjs',
  'scripts/scan-secrets.mjs',
  'scripts/promote-product.mjs',
  'products/general/product.json',
  'products/README.md',
  'products/catalog.json',
  'products/product-catalog.schema.json',
  'products/product.schema.json',
  'products/ppt-designer/product.json',
  'products/ai-otome/product.json',
  'PRODUCT.md',
  'PRODUCT_UIUX.md',
  'DESIGN.md',
  'docs/README.md',
  'docs/PRODUCT_MODEL_CONTRACT.md',
  'runtimes/hermes-agent/run_agent.py',
  'runtimes/hermes-agent/UPSTREAM.md',
  'runtimes/hermes-agent/PATCHES.md',
  'docs/architecture/PRODUCTION_REPOSITORY_PLAN.md',
  'docs/architecture/HERMES_VENDORING.md',
  'docs/references/REFERENCE_PROJECTS.md',
  'experiments/README.md',
  'runtimes/README.md',
  '.github/CODEOWNERS',
  '.github/workflows/verify.yml',
  '.github/dependabot.yml',
  '.github/pull_request_template.md',
  '.github/ISSUE_TEMPLATE/config.yml',
  '.github/ISSUE_TEMPLATE/bug_report.yml',
  '.github/ISSUE_TEMPLATE/feature_request.yml',
  '.github/ISSUE_TEMPLATE/product_example.yml',
  'LICENSE',
  '.env.example',
  'apps/webui/requirements.txt',
  'apps/webui/requirements-dev.txt',
]

const currentDocPaths = [
  'README.md',
  'NOTICE.md',
  'CHANGELOG.md',
  'RELEASE.md',
  'PRODUCT.md',
  'PRODUCT_UIUX.md',
  'DESIGN.md',
  'CODE_OF_CONDUCT.md',
  'CONTRIBUTING.md',
  'SECURITY.md',
  'docs/README.md',
  'docs/PRODUCT_MODEL_CONTRACT.md',
  'docs/architecture/PRODUCTION_REPOSITORY_PLAN.md',
  'docs/architecture/HERMES_VENDORING.md',
  'docs/references/REFERENCE_PROJECTS.md',
  'runtimes/README.md',
  'apps/webui/README.md',
  'apps/webui/AGENTS.md',
  'apps/webui/CONTRIBUTING.md',
]

const publicDocDirs = [
  'docs/references',
  'docs/research',
]

const staleCurrentDocPatterns = [
  [/\bNext AI\b/, 'current docs should use the Knead product name'],
  [/\bNEXT_AI_/, 'current docs should use KNEAD_* environment names'],
  [/nextaichat/i, 'current docs should not refer to the old repository name'],
  [/private GitHub|private repository/i, 'current docs should use release-ready repository language'],
  [/唯一事实|唯一准则/, 'current docs should not claim a single competing source of truth'],
]

const publicDocPatterns = [
  [/\bNext AI\b/, 'public reference docs should use the Knead product name'],
  [/\/Users\//, 'public reference docs must not contain local absolute paths'],
  [/nextaichat/i, 'public reference docs should not refer to the old repository name'],
]

const creatorShellClassifierSnippets = [
  'const isPpt =',
  'const isPitch =',
  'const isSales =',
  'const isResearch =',
  'const isData =',
  'const isImage =',
  "return 'PPT Designer'",
  "return '图片生成器'",
  "return '头像图片生成器'",
  "return '海报图片生成器'",
  "return '插画图片生成器'",
  "return '研究分析师'",
  "return '数据分析师'",
  "return '行业研究产品'",
  "return '竞品研究产品'",
  "return '运营数据分析师'",
  "return 'Fundraising Deck AI'",
  "return 'Sales Deck AI'",
]

const DEFAULT_RELEASE_REPO_BASE = 'https://github.com/1zhangyy1/knead'

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

function gitStatusFiles() {
  const result = spawnSync('git', ['status', '--porcelain=v1', '--untracked-files=all'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  if (result.status !== 0) {
    throw new Error(result.stderr || 'git status failed')
  }
  return result.stdout
    .split('\n')
    .filter(Boolean)
    .map((line) => line.slice(3).replace(/^"|"$/g, ''))
}

let failed = false
const trackedFiles = gitLsFiles()
const workingTreeFiles = gitStatusFiles()

function readBuiltinProductIds() {
  const catalog = readJson('products/catalog.json')
  if (!catalog) return []
  if (!Array.isArray(catalog.builtins)) {
    console.error('INVALID product catalog: products/catalog.json builtins must be an array')
    failed = true
    return []
  }
  const ids = []
  const seen = new Set()
  for (const [index, item] of catalog.builtins.entries()) {
    const label = `products/catalog.json builtins[${index}]`
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      console.error(`INVALID product catalog: ${label} must be an object`)
      failed = true
      continue
    }
    if (typeof item.id !== 'string' || !item.id.trim()) {
      console.error(`INVALID product catalog: ${label}.id must be a non-empty string`)
      failed = true
      continue
    }
    if (seen.has(item.id)) {
      console.error(`INVALID product catalog: duplicate id ${item.id}`)
      failed = true
    }
    seen.add(item.id)
    ids.push(item.id)
  }
  return ids
}

const builtinProductIds = readBuiltinProductIds()
const allowedTrackedProductRoots = new Set([
  ...staticAllowedProductRoots,
  ...builtinProductIds,
])

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch (error) {
    console.error(`INVALID JSON: ${path}`)
    console.error(`  ${error instanceof Error ? error.message : String(error)}`)
    failed = true
    return null
  }
}

function githubRepoBaseFromUrl(rawUrl) {
  if (typeof rawUrl !== 'string') return null
  let url = rawUrl.trim().replace(/^git\+/, '')
  if (url.startsWith('git@github.com:')) {
    url = `https://github.com/${url.slice('git@github.com:'.length)}`
  }
  const match = url.match(/^https:\/\/(?:[^@/]+@)?github\.com\/([^/#?]+\/[^/#?]+?)(?:\.git)?(?:[#?].*)?$/)
  if (!match) return null
  return `https://github.com/${match[1].replace(/\.git$/, '')}`
}

function gitOriginRepoBase() {
  const result = spawnSync('git', ['remote', 'get-url', 'origin'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  if (result.status !== 0) {
    console.error('MISSING Git origin: package metadata must be checked against the release repository remote')
    failed = true
    return null
  }
  const base = githubRepoBaseFromUrl(result.stdout.trim())
  if (!base) {
    console.error(`INVALID Git origin: expected a GitHub repository URL, got ${result.stdout.trim() || '(empty)'}`)
    failed = true
    return null
  }
  return base
}

function releaseRepoBase() {
  const rawValue = process.env.KNEAD_RELEASE_REPOSITORY || process.env.KNEAD_RELEASE_REPO_URL
  if (!rawValue) return DEFAULT_RELEASE_REPO_BASE

  const base = githubRepoBaseFromUrl(rawValue)
  if (!base) {
    console.error(`INVALID release repository: expected a GitHub repository URL, got ${rawValue}`)
    failed = true
    return null
  }
  return base
}

function assertPackageRepositoryMetadata(pkg) {
  const expectedBase = releaseRepoBase()
  if (!expectedBase) return

  const expectedRepository = `git+${expectedBase}.git`
  const expectedBugs = `${expectedBase}/issues`
  const expectedHomepage = `${expectedBase}#readme`

  if (pkg.repository?.url !== expectedRepository) {
    console.error('INVALID package metadata: package.json repository.url must match the release repository')
    console.error(`  expected ${expectedRepository}`)
    failed = true
  }
  if (pkg.bugs?.url !== expectedBugs) {
    console.error('INVALID package metadata: package.json bugs.url must match the release repository')
    console.error(`  expected ${expectedBugs}`)
    failed = true
  }
  if (pkg.homepage !== expectedHomepage) {
    console.error('INVALID package metadata: package.json homepage must match the release repository')
    console.error(`  expected ${expectedHomepage}`)
    failed = true
  }
}

function assertPackageMetadata() {
  const pkg = readJson('package.json')
  if (!pkg) return

  const stringFields = ['name', 'version', 'description', 'license', 'homepage', 'packageManager']
  for (const field of stringFields) {
    if (typeof pkg[field] !== 'string' || !pkg[field].trim()) {
      console.error(`MISSING package metadata: package.json ${field}`)
      failed = true
    }
  }

  if (pkg.private !== true) {
    console.error('MISSING package metadata: root package.json should stay private for the pnpm workspace')
    failed = true
  }
  const readme = existsSync('README.md') ? readFileSync('README.md', 'utf8') : ''
  if (pkg.private === true && !/private:\s*true[\s\S]*accidental registry publishes/i.test(readme)) {
    console.error('MISSING package metadata docs: README.md should explain why root package.json stays private')
    failed = true
  }

  if (!pkg.repository || pkg.repository.type !== 'git' || typeof pkg.repository.url !== 'string') {
    console.error('MISSING package metadata: package.json repository must point at the public Git repository')
    failed = true
  }

  if (!pkg.bugs || typeof pkg.bugs.url !== 'string') {
    console.error('MISSING package metadata: package.json bugs.url is required')
    failed = true
  }

  assertPackageRepositoryMetadata(pkg)

  if (!pkg.engines || pkg.engines.node !== '>=22' || pkg.engines.pnpm !== '>=10.33' || pkg.engines.python !== '>=3.11') {
    console.error('MISSING package metadata: package.json engines must declare Node, pnpm, and Python requirements')
    failed = true
  }

  if (!Array.isArray(pkg.keywords) || pkg.keywords.length < 3) {
    console.error('MISSING package metadata: package.json keywords should describe the project for open-source readers')
    failed = true
  }
}

function assertPackageScriptExecutables() {
  const pkg = readJson('package.json')
  if (!pkg || !pkg.scripts) return

  for (const [name, command] of Object.entries(pkg.scripts)) {
    if (typeof command !== 'string') continue
    const firstToken = command.trim().split(/\s+/)[0]
    if (!firstToken.startsWith('scripts/') || !firstToken.endsWith('.sh')) continue
    if (!existsSync(firstToken)) {
      console.error(`MISSING package script target: package.json scripts.${name} points to ${firstToken}`)
      failed = true
      continue
    }
    if ((statSync(firstToken).mode & 0o111) === 0) {
      console.error(`INVALID package script target: ${firstToken} must be executable because package.json scripts.${name} runs it directly`)
      failed = true
    }
  }
}

function assertPnpmWorkspaceMetadata() {
  if (!existsSync('pnpm-lock.yaml') || !existsSync('pnpm-workspace.yaml')) return

  const workspace = readFileSync('pnpm-workspace.yaml', 'utf8')
  if (!/packages:\s*\n\s*-\s+packages\/\*/.test(workspace)) {
    console.error('INVALID pnpm workspace: pnpm-workspace.yaml should include packages/*')
    failed = true
  }

  const lockfile = readFileSync('pnpm-lock.yaml', 'utf8')
  const importersBlock = lockfile.match(/importers:\n([\s\S]*?)\npackages:/)
  if (!importersBlock) {
    console.error('INVALID pnpm lockfile: missing importers block')
    failed = true
    return
  }

  const importers = importersBlock[1]
    .split('\n')
    .map((line) => line.match(/^  ([^ ].*?):(?:\s*\{\})?\s*$/)?.[1])
    .filter(Boolean)
  const expected = ['.', 'packages/hermes-client', 'packages/space-runtime']
  const unexpected = importers.filter((item) => !expected.includes(item))
  const missing = expected.filter((item) => !importers.includes(item))

  for (const item of unexpected) {
    console.error(`STALE pnpm lockfile importer: ${item}`)
    console.error('  pnpm-lock.yaml should match the production workspace; experiments are not workspace projects')
    failed = true
  }
  for (const item of missing) {
    console.error(`MISSING pnpm lockfile importer: ${item}`)
    failed = true
  }
}

function assertPythonRequirements() {
  const runtimePath = 'apps/webui/requirements.txt'
  const devPath = 'apps/webui/requirements-dev.txt'
  if (!existsSync(runtimePath) || !existsSync(devPath)) return

  const devRequirements = readFileSync(devPath, 'utf8')
  if (!devRequirements.includes('-r requirements.txt')) {
    console.error(`MISSING Python dependency link: ${devPath} must include ${runtimePath}`)
    console.error('  CI and local setup install dev requirements, so they must include runtime requirements too.')
    failed = true
  }
  if (!/^\s*pytest(?:[<>=~!].*)?$/m.test(devRequirements)) {
    console.error(`MISSING Python test dependency: ${devPath} must include pytest`)
    console.error('  pnpm verify runs the product pytest suite in CI and local release checks.')
    failed = true
  }
}

function assertNoticeContent() {
  const path = 'NOTICE.md'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  for (const phrase of [
    'Hermes Agent Runtime',
    'Inherited WebUI Code',
    'Built-in Product Examples',
    'apps/webui/LICENSE',
    'products/ppt-designer/ppt-skill',
    'runtimes/hermes-agent/LICENSE',
    'assets/CREDITS.md',
  ]) {
    if (!content.includes(phrase)) {
      console.error(`MISSING notice language: ${path} should mention ${phrase}`)
      failed = true
    }
  }
}

function assertLicensingBoundary() {
  const rootLicensePath = 'LICENSE'
  const webuiLicensePath = 'apps/webui/LICENSE'
  const hermesLicensePath = 'runtimes/hermes-agent/LICENSE'
  const upstreamPath = 'runtimes/hermes-agent/UPSTREAM.md'
  const patchesPath = 'runtimes/hermes-agent/PATCHES.md'

  if (existsSync(rootLicensePath)) {
    const content = readFileSync(rootLicensePath, 'utf8')
    for (const phrase of ['MIT License', 'Copyright (c) 2026 Knead Contributors']) {
      if (!content.includes(phrase)) {
        console.error(`INVALID root license: ${rootLicensePath} should mention ${phrase}`)
        failed = true
      }
    }
  }

  if (existsSync(webuiLicensePath)) {
    const content = readFileSync(webuiLicensePath, 'utf8')
    for (const phrase of ['MIT License', 'Copyright (c) 2025 Hermes Web UI Contributors']) {
      if (!content.includes(phrase)) {
        console.error(`INVALID WebUI license: ${webuiLicensePath} should mention ${phrase}`)
        failed = true
      }
    }
  }

  if (existsSync(hermesLicensePath)) {
    const content = readFileSync(hermesLicensePath, 'utf8')
    for (const phrase of ['MIT License', 'Copyright (c) 2025 Nous Research']) {
      if (!content.includes(phrase)) {
        console.error(`INVALID Hermes license: ${hermesLicensePath} should mention ${phrase}`)
        failed = true
      }
    }
  }

  if (existsSync(upstreamPath)) {
    const content = readFileSync(upstreamPath, 'utf8')
    for (const phrase of [
      'https://github.com/NousResearch/hermes-agent',
      'Vendored commit:',
      'Import method:',
    ]) {
      if (!content.includes(phrase)) {
        console.error(`MISSING Hermes upstream metadata: ${upstreamPath} should mention ${phrase}`)
        failed = true
      }
    }
  }

  if (existsSync(patchesPath)) {
    const content = readFileSync(patchesPath, 'utf8')
    for (const phrase of ['Runtime code patches:', 'Metadata patches:']) {
      if (!content.includes(phrase)) {
        console.error(`MISSING Hermes patch metadata: ${patchesPath} should mention ${phrase}`)
        failed = true
      }
    }
  }
}

function collectMarkdownFiles(dir) {
  if (!existsSync(dir)) return []
  const files = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`
    if (entry.name.startsWith('.')) continue
    if (entry.isDirectory()) {
      files.push(...collectMarkdownFiles(path))
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      files.push(path)
    }
  }
  return files
}

function assertProductGitignoreAllowlist() {
  if (!existsSync('.gitignore')) return
  const gitignore = readFileSync('.gitignore', 'utf8')
  for (const rule of [
    'products/**/.knead-published.json',
    'products/**/*.lock',
    'products/**/*.pptx',
  ]) {
    if (!gitignore.includes(rule)) {
      console.error(`MISSING product runtime ignore rule: ${rule}`)
      console.error('  Built-in product directories are source, but local runs can create runtime artifacts that must stay out of Git.')
      failed = true
    }
  }
  for (const productId of builtinProductIds) {
    const dirRule = `!products/${productId}/`
    const subtreeRule = `!products/${productId}/**`
    if (!gitignore.includes(dirRule) || !gitignore.includes(subtreeRule)) {
      console.error(`MISSING product source allowlist: ${productId}`)
      console.error(`  products/catalog.json lists ${productId}, but .gitignore does not allow both ${dirRule} and ${subtreeRule}`)
      failed = true
    }
  }
}

function assertProductSchemaBoundary() {
  const path = 'products/product.schema.json'
  if (!existsSync(path)) return
  const schema = readJson(path)
  if (!schema) return

  if (schema.additionalProperties !== false) {
    console.error('INVALID product schema: products/product.schema.json must reject unknown top-level manifest fields')
    console.error('  Product-specific extension data belongs under metadata or config, not arbitrary product.json fields.')
    failed = true
  }

  for (const field of ['metadata', 'config']) {
    if (!schema.properties?.[field] || schema.properties[field].additionalProperties !== true) {
      console.error(`INVALID product schema: products/product.schema.json must expose ${field} as an explicit extension slot`)
      failed = true
    }
  }
}

function assertReleaseCheckGate() {
  const path = 'scripts/release-check.mjs'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  if (!content.includes("'pnpm', ['install', '--frozen-lockfile']")) {
    console.error('MISSING release gate: scripts/release-check.mjs must run pnpm install --frozen-lockfile')
    console.error('  Public releases should fail early when package.json and pnpm-lock.yaml drift.')
    failed = true
  }
  if (!content.includes("'git', ['diff', '--check']")) {
    console.error('MISSING release gate: scripts/release-check.mjs must run git diff --check')
    failed = true
  }
  if (!content.includes("'git', ['diff', '--cached', '--check']")) {
    console.error('MISSING release gate: scripts/release-check.mjs must run git diff --cached --check')
    failed = true
  }
  if (!content.includes("'node', ['scripts/release-batches.mjs', '--check']")) {
    console.error('MISSING release gate: scripts/release-check.mjs must run the release batch classification check')
    failed = true
  }
  if (!content.includes("'pnpm', ['check']")) {
    console.error('MISSING release gate: scripts/release-check.mjs must run pnpm check')
    failed = true
  }
  if (!content.includes("'git', ['status', '--porcelain=v1']")) {
    console.error('MISSING release gate: scripts/release-check.mjs must support clean worktree checks before tagging')
    failed = true
  }
}

function assertLocalArtifactCleaner() {
  const path = 'scripts/clean-local-artifacts.mjs'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  for (const phrase of ["entry.name === 'package-lock.json'", "entry.name.startsWith('.tmp-')", 'productsRoot', 'experimentsRoot', 'tsbuildinfo']) {
    if (!content.includes(phrase)) {
      console.error(`MISSING local artifact cleaner coverage: ${path} should mention ${phrase}`)
      failed = true
    }
  }
}

function assertReleaseScripts() {
  const pkg = readJson('package.json')
  if (!pkg || !pkg.scripts) return
  if (pkg.scripts['release:check:clean'] !== 'node scripts/release-check.mjs --require-clean') {
    console.error('MISSING package release script: package.json must define release:check:clean')
    failed = true
  }
  if (pkg.scripts['release:batches'] !== 'node scripts/release-batches.mjs') {
    console.error('MISSING package release script: package.json must define release:batches')
    failed = true
  }
  if (pkg.scripts['docs:check'] !== 'node scripts/check-markdown-links.mjs') {
    console.error('MISSING package docs script: package.json must define docs:check')
    failed = true
  }
}

function assertVerifyGate() {
  const path = 'scripts/verify.mjs'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  if (!content.includes("'node', ['scripts/check-source-whitespace.mjs']")) {
    console.error('MISSING verify gate: scripts/verify.mjs must run the source whitespace check')
    failed = true
  }
  if (!content.includes("'node', ['scripts/check-markdown-links.mjs']")) {
    console.error('MISSING verify gate: scripts/verify.mjs must run the Markdown link check')
    failed = true
  }
  if (!content.includes("'node', ['scripts/scan-secrets.mjs', '--self-test']")) {
    console.error('MISSING verify gate: scripts/verify.mjs must run the secret scanner self-test')
    failed = true
  }
  for (const script of ['scripts/dev-webui.sh', 'scripts/setup-local.sh', 'scripts/hermes-local.sh']) {
    if (!content.includes(`'bash', ['-n', '${script}']`)) {
      console.error(`MISSING verify gate: scripts/verify.mjs must syntax-check ${script}`)
      failed = true
    }
  }
}

function assertSecretScannerCoverage() {
  const path = 'scripts/scan-secrets.mjs'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  for (const phrase of [
    "'DESIGN.md'",
    "'apps/webui/static/'",
    "'apps/webui/api/'",
    "'products/'",
    "'scripts/'",
    "'docs/'",
    "'.github/'",
    "isReleaseOwnedPath('apps/webui/tests/test_product_drafts.py')",
    "isReleaseOwnedPath('DESIGN.md')",
  ]) {
    if (!content.includes(phrase)) {
      console.error(`MISSING secret scanner coverage: ${path} should mention ${phrase}`)
      failed = true
    }
  }
}

function assertPullRequestTemplate() {
  const path = '.github/pull_request_template.md'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  for (const phrase of ['.hermes-home', 'published-draft markers', 'pnpm product:check', 'Product Shape', 'assets/CREDITS.md']) {
    if (!content.includes(phrase)) {
      console.error(`MISSING PR checklist language: ${path} should mention ${phrase}`)
      failed = true
    }
  }
}

function assertIssueTemplateConfig() {
  const path = '.github/ISSUE_TEMPLATE/config.yml'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  for (const phrase of ['blank_issues_enabled: false', 'Security vulnerability', '/security/policy']) {
    if (!content.includes(phrase)) {
      console.error(`MISSING issue template config language: ${path} should mention ${phrase}`)
      failed = true
    }
  }
  const expectedBase = releaseRepoBase()
  if (expectedBase) {
    for (const expectedUrl of [`${expectedBase}/security/policy`, `${expectedBase}#readme`]) {
      if (!content.includes(expectedUrl)) {
        console.error(`INVALID issue template link: ${path} must reference ${expectedUrl}`)
        failed = true
      }
    }
  }
}

function assertVerifyWorkflow() {
  const path = '.github/workflows/verify.yml'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  for (const phrase of [
    'workflow_dispatch:',
    'permissions:',
    'contents: read',
    'concurrency:',
    'cancel-in-progress: true',
    'timeout-minutes:',
    'actions/setup-python',
    'python -m pip install -r apps/webui/requirements-dev.txt',
    'pnpm release:check',
  ]) {
    if (!content.includes(phrase)) {
      console.error(`MISSING verify workflow hardening: ${path} should mention ${phrase}`)
      failed = true
    }
  }
  const installIndex = content.indexOf('python -m pip install -r apps/webui/requirements-dev.txt')
  const releaseIndex = content.indexOf('pnpm release:check')
  if (installIndex === -1 || releaseIndex === -1 || installIndex > releaseIndex) {
    console.error(`INVALID verify workflow order: ${path} must install Python dev requirements before pnpm release:check`)
    failed = true
  }
}

function assertCodeowners() {
  const path = '.github/CODEOWNERS'
  if (!existsSync(path)) return
  const content = readFileSync(path, 'utf8')
  if (!content.includes('* @1zhangyy1')) {
    console.error(`MISSING repository owner: ${path} must assign default ownership to @1zhangyy1`)
    failed = true
  }
}

for (const file of trackedFiles) {
  for (const [pattern, reason] of forbiddenTrackedPatterns) {
    if (pattern.test(file)) {
      console.error(`FORBIDDEN tracked file: ${file}`)
      console.error(`  ${reason}`)
      failed = true
    }
  }
  const productMatch = file.match(/^products\/([^/]+)/)
  if (productMatch && !allowedTrackedProductRoots.has(productMatch[1])) {
    console.error(`FORBIDDEN tracked product: ${file}`)
    console.error('  products/ is source-only for curated built-in examples; user-created products belong in runtime state')
    failed = true
  }
}

for (const file of workingTreeFiles) {
  for (const [pattern, reason] of forbiddenTrackedPatterns) {
    if (pattern.test(file)) {
      console.error(`FORBIDDEN working tree file: ${file}`)
      console.error(`  ${reason}`)
      failed = true
    }
  }
}

if (existsSync('products')) {
  for (const entry of readdirSync('products', { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue
    if (!allowedTrackedProductRoots.has(entry.name)) {
      const type = entry.isDirectory() ? 'directory' : 'file'
      console.error(`FORBIDDEN products/ root ${type}: products/${entry.name}`)
      console.error('  products/ may contain only curated built-in examples; generated products belong in runtime state')
      failed = true
    }
  }
}

if (existsSync('docs')) {
  for (const entry of readdirSync('docs', { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue
    if (!allowedDocsRootEntries.has(entry.name)) {
      const type = entry.isDirectory() ? 'directory' : 'file'
      console.error(`FORBIDDEN docs/ root ${type}: docs/${entry.name}`)
      console.error('  docs/ root should contain only current entry points and categorized folders')
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

assertProductGitignoreAllowlist()
assertProductSchemaBoundary()
assertReleaseCheckGate()
assertLocalArtifactCleaner()
assertReleaseScripts()
assertVerifyGate()
assertSecretScannerCoverage()
assertVerifyWorkflow()
assertCodeowners()
assertPullRequestTemplate()
assertIssueTemplateConfig()
assertPackageMetadata()
assertPackageScriptExecutables()
assertPnpmWorkspaceMetadata()
assertPythonRequirements()
assertNoticeContent()
assertLicensingBoundary()

for (const docPath of currentDocPaths) {
  if (!existsSync(docPath)) {
    continue
  }
  const content = readFileSync(docPath, 'utf8')
  for (const [pattern, reason] of staleCurrentDocPatterns) {
    if (pattern.test(content)) {
      console.error(`STALE current doc language: ${docPath}`)
      console.error(`  ${reason}`)
      failed = true
    }
  }
}

for (const docDir of publicDocDirs) {
  for (const docPath of collectMarkdownFiles(docDir)) {
    const content = readFileSync(docPath, 'utf8')
    for (const [pattern, reason] of publicDocPatterns) {
      if (pattern.test(content)) {
        console.error(`STALE public doc language: ${docPath}`)
        console.error(`  ${reason}`)
        failed = true
      }
    }
  }
}

const creatorShell = 'apps/webui/static/product-shell-runtime.js'
if (existsSync(creatorShell)) {
  const content = readFileSync(creatorShell, 'utf8')
  for (const snippet of creatorShellClassifierSnippets) {
    if (content.includes(snippet)) {
      console.error(`STALE Creator shell classifier: ${creatorShell}`)
      console.error(`  Creator should decide product semantics; remove hardcoded title return: ${snippet}`)
      failed = true
    }
  }
}

if (failed) {
  process.exit(1)
}

console.log('Repository audit passed')
