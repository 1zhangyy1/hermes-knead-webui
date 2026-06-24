#!/usr/bin/env node

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, statSync } from 'node:fs'

const maxFileBytes = 2 * 1024 * 1024
const selfTest = process.argv.includes('--self-test')
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
  'node_modules/',
  'runtimes/hermes-agent/',
  'vendor/',
  'products/ppt-designer/outputs/',
  'products/ppt-designer/versions/',
]

const ignoredPathSegments = [
  '/node_modules/',
  '/__pycache__/',
  '/.pytest_cache/',
  '/.venv/',
  '/.venv311/',
]

const secretPatterns = [
  {
    name: 'OpenAI-style API key',
    regex: /\b(?:sk|sk-ant|sk-proj|sk-or-v1|fal)-[A-Za-z0-9][A-Za-z0-9_-]{16,}\b/g,
    value: (match) => match[0],
  },
  {
    name: 'provider env key assignment',
    regex: /\b(?:OPENAI|ANTHROPIC|OPENROUTER|DEEPSEEK|GEMINI|GOOGLE|FAL|REPLICATE|TOGETHER|MISTRAL|GROQ|XAI)_(?:API_)?KEY\s*=\s*([^\s#'"`]+)/gi,
    value: (match) => match[1],
  },
  {
    name: 'credential field',
    regex: /\b(?:api[_]?key|apiKey|secret|token|password|credential|private[_]?key|privateKey)\s*[:=]\s*['"]([^'"]{12,})['"]/g,
    value: (match) => match[1],
  },
]

const placeholderPatterns = [
  /^$/,
  /^<.*>$/,
  /^\$\{.*\}$/,
  /\.\.\./,
  /^(your|my|example|sample|placeholder|dummy|fake|test|old|correct|current|fallback|profile|local|secret-from|token-from)[-_a-z0-9]*$/i,
  /test/i,
  /fake/i,
  /example/i,
  /placeholder/i,
  /your-/i,
  /^x+$/i,
  /^header\.payload\.signature$/i,
]

const rootReleaseFiles = new Set([
  '.env.example',
  '.gitattributes',
  '.gitignore',
  'CHANGELOG.md',
  'CODE_OF_CONDUCT.md',
  'CONTRIBUTING.md',
  'DESIGN.md',
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

function isPlaceholder(value) {
  const normalized = String(value || '').trim()
  return placeholderPatterns.some((pattern) => pattern.test(normalized))
}

function lineNumberForOffset(text, offset) {
  let line = 1
  for (let index = 0; index < offset; index += 1) {
    if (text.charCodeAt(index) === 10) line += 1
  }
  return line
}

function scanTextForSecrets(text, file) {
  const findings = []

  for (const pattern of secretPatterns) {
    pattern.regex.lastIndex = 0
    for (const match of text.matchAll(pattern.regex)) {
      const value = pattern.value(match)
      if (isPlaceholder(value)) continue
      findings.push({
        file,
        line: lineNumberForOffset(text, match.index || 0),
        name: pattern.name,
      })
    }
  }

  return findings
}

function assertSelfTest(condition, message) {
  if (!condition) {
    console.error(`Secret scanner self-test failed: ${message}`)
    process.exit(1)
  }
}

function runSelfTest() {
  const openAiStyle = 'sk' + '-proj-' + 'a'.repeat(24)
  const falStyle = 'fal' + '-' + 'b'.repeat(24)
  const genericCredential = 'c'.repeat(24)
  const dangerousText = [
    `OPENAI_API_KEY=${openAiStyle}`,
    `FAL_KEY=${falStyle}`,
    `apiKey: "${genericCredential}"`,
  ].join('\n')
  const safeText = [
    'OPENAI_API_KEY=your-openai-key',
    'FAL_KEY=<your-fal-key>',
    'token: "example-token-value"',
  ].join('\n')

  const dangerousFindings = scanTextForSecrets(dangerousText, 'self-test.env')
  const safeFindings = scanTextForSecrets(safeText, 'self-test.env')

  assertSelfTest(dangerousFindings.length >= 3, 'expected provider keys and credential fields to be detected')
  assertSelfTest(safeFindings.length === 0, 'expected placeholders to be ignored')
  assertSelfTest(isReleaseOwnedPath('scripts/scan-secrets.mjs'), 'expected release-owned scripts to be scanned')
  assertSelfTest(isReleaseOwnedPath('DESIGN.md'), 'expected design system docs to be scanned')
  assertSelfTest(isReleaseOwnedPath('apps/webui/README.md'), 'expected WebUI README to be scanned')
  assertSelfTest(isReleaseOwnedPath('apps/webui/requirements-dev.txt'), 'expected Python requirement files to be scanned')
  assertSelfTest(isReleaseOwnedPath('apps/webui/tests/test_product_drafts.py'), 'expected product-layer tests to be scanned')
  assertSelfTest(!shouldSkipPath('apps/webui/tests/test_product_drafts.py'), 'expected product-layer tests not to be skipped')
  assertSelfTest(isReleaseOwnedPath('runtimes/README.md'), 'expected runtime README to be scanned')
  assertSelfTest(!isReleaseOwnedPath('runtimes/hermes-agent/run_agent.py'), 'expected vendored runtime internals outside release scan')
  assertSelfTest(shouldSkipPath('.hermes-home/webui/state.json'), 'expected local Hermes state to be skipped')

  console.log('Secret scanner self-test passed')
}

if (selfTest) {
  runSelfTest()
  process.exit(0)
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

  for (const finding of scanTextForSecrets(text, file)) {
    console.error(`POSSIBLE SECRET (${finding.name}): ${finding.file}:${finding.line}`)
    console.error('  Replace real credentials with placeholders and keep local values in ignored .env files.')
    failed = true
  }
}

if (failed) {
  process.exit(1)
}

console.log('Secret scan passed')
