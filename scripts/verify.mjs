#!/usr/bin/env node

import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const localVenvPython = join(repoRoot, 'apps', 'webui', '.venv311', 'bin', 'python')
const python = process.env.HERMES_WEBUI_PYTHON || (existsSync(localVenvPython) ? localVenvPython : 'python3')

const checks = [
  ['repository audit', 'node', ['scripts/audit-repo.mjs']],
  ['source whitespace', 'node', ['scripts/check-source-whitespace.mjs']],
  ['markdown links', 'node', ['scripts/check-markdown-links.mjs']],
  ['secret scan', 'node', ['scripts/scan-secrets.mjs']],
  ['secret scanner self-test', 'node', ['scripts/scan-secrets.mjs', '--self-test']],
  [
    'python api compile',
    python,
    [
      '-m',
      'py_compile',
      'apps/webui/api/products.py',
      'apps/webui/api/product_context.py',
      'apps/webui/api/routes.py',
      'apps/webui/api/updates.py',
    ],
  ],
  ['product runtime syntax', 'node', ['--check', 'apps/webui/static/product-runtime.js']],
  ['product store syntax', 'node', ['--check', 'apps/webui/static/product-store.js']],
  ['product shell syntax', 'node', ['--check', 'apps/webui/static/product-shell-runtime.js']],
  ['workspace syntax', 'node', ['--check', 'apps/webui/static/workspace.js']],
  ['ppt product syntax', 'node', ['--check', 'products/ppt-designer/app.js']],
  ['built-in product manifest syntax', 'node', ['--check', 'scripts/verify-products.mjs']],
  ['product promotion helper syntax', 'node', ['--check', 'scripts/promote-product.mjs']],
  ['built-in product manifests', 'node', ['scripts/verify-products.mjs']],
  ['candidate product manifest check', 'node', ['scripts/verify-products.mjs', '--candidate', 'products/general']],
  ['release check syntax', 'node', ['--check', 'scripts/release-check.mjs']],
  ['release batches syntax', 'node', ['--check', 'scripts/release-batches.mjs']],
  ['webui smoke syntax', 'node', ['--check', 'scripts/webui-smoke.mjs']],
  ['local artifact cleaner syntax', 'node', ['--check', 'scripts/clean-local-artifacts.mjs']],
  ['live Hermes smoke syntax', 'node', ['--check', 'scripts/hermes-smoke.mjs']],
  ['dev shell syntax', 'bash', ['-n', 'scripts/dev-webui.sh']],
  ['local setup shell syntax', 'bash', ['-n', 'scripts/setup-local.sh']],
  ['Hermes helper shell syntax', 'bash', ['-n', 'scripts/hermes-local.sh']],
  ['product core smoke', python, ['scripts/verify-product-core.py']],
  [
    'product pytest suite',
    python,
    [
      '-m',
      'pytest',
      'apps/webui/tests/test_product_drafts.py',
      'apps/webui/tests/test_product_scope_lines.py',
      'apps/webui/tests/test_product_shell_static.py',
      'apps/webui/tests/test_product_storage_boundaries.py',
      'apps/webui/tests/test_product_ui_status.py',
      'apps/webui/tests/test_streaming_runtime_prompt.py',
      '-q',
    ],
  ],
  ['webui http smoke', 'node', ['scripts/webui-smoke.mjs']],
]

let failed = false

for (const [name, command, args] of checks) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    stdio: 'inherit',
  })
  if (result.status === 0) {
    console.log(`PASS ${name}`)
  } else {
    console.error(`FAIL ${name}`)
    failed = true
  }
}

if (failed) {
  process.exit(1)
}
