#!/usr/bin/env node

import { spawnSync } from 'node:child_process'

const checks = [
  ['repository audit', 'node', ['scripts/audit-repo.mjs']],
  [
    'python api compile',
    'python3',
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
]

let failed = false

for (const [name, command, args] of checks) {
  const result = spawnSync(command, args, {
    cwd: new URL('..', import.meta.url),
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
