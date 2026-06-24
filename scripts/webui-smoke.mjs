#!/usr/bin/env node

import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import net from 'node:net'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const python = process.env.HERMES_WEBUI_PYTHON || 'python3'
const host = '127.0.0.1'
const timeoutMs = Number(process.env.KNEAD_WEBUI_SMOKE_TIMEOUT_MS || 20000)
const productCatalog = JSON.parse(readFileSync(join(repoRoot, 'products', 'catalog.json'), 'utf8'))
const builtinProductIds = Array.isArray(productCatalog.builtins)
  ? productCatalog.builtins.map((item) => item && item.id).filter(Boolean)
  : []
if (!builtinProductIds.length) fail('products/catalog.json must list at least one built-in product')

function fail(message) {
  throw new Error(message)
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.on('error', reject)
    server.listen(0, host, () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close(() => resolve(port))
    })
  })
}

async function waitForJson(url, predicate) {
  const deadline = Date.now() + timeoutMs
  let lastError = ''
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url)
      const text = await res.text()
      if (res.ok) {
        const json = JSON.parse(text)
        if (predicate(json)) return json
      }
      lastError = `${res.status} ${res.statusText}: ${text.slice(0, 240)}`
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error)
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  fail(`Timed out waiting for ${url}\nLast error: ${lastError}`)
}

async function getText(url) {
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) fail(`${url} returned ${res.status} ${res.statusText}\n${text.slice(0, 500)}`)
  return { text, contentType: res.headers.get('content-type') || '' }
}

async function getJson(url) {
  const { text } = await getText(url)
  return JSON.parse(text)
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body || {}),
  })
  const text = await res.text()
  let json
  try {
    json = text ? JSON.parse(text) : {}
  } catch (error) {
    fail(`${url} returned non-JSON response ${res.status} ${res.statusText}\n${text.slice(0, 500)}`)
  }
  if (!res.ok) fail(`${url} returned ${res.status} ${res.statusText}\n${text.slice(0, 500)}`)
  return json
}

async function main() {
  const port = await getFreePort()
  const stateRoot = mkdtempSync(join(tmpdir(), 'knead-webui-smoke-'))
  const stateDir = join(stateRoot, 'webui-state')
  const hermesHome = join(stateRoot, 'hermes-home')
  const runtimeProducts = join(stateDir, 'products')
  const baseUrl = `http://${host}:${port}`
  const env = {
    ...process.env,
    HERMES_HOME: hermesHome,
    HERMES_WEBUI_STATE_DIR: stateDir,
    HERMES_WEBUI_HOST: host,
    HERMES_WEBUI_PORT: String(port),
    HERMES_WEBUI_AUTO_INSTALL: '0',
    HERMES_WEBUI_TEST_NETWORK_BLOCK: '1',
    HERMES_WEBUI_AGENT_DIR: join(repoRoot, 'runtimes', 'hermes-agent'),
    KNEAD_PROJECT_ROOT: repoRoot,
    KNEAD_BUILTIN_PRODUCTS_DIR: join(repoRoot, 'products'),
    KNEAD_PRODUCTS_DIR: runtimeProducts,
  }

  const proc = spawn(python, [join(repoRoot, 'apps', 'webui', 'server.py')], {
    cwd: repoRoot,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let output = ''
  proc.stdout.on('data', (chunk) => { output += chunk.toString() })
  proc.stderr.on('data', (chunk) => { output += chunk.toString() })

  try {
    await waitForJson(`${baseUrl}/health`, (json) => json && json.status === 'ok')

    const home = await getText(`${baseUrl}/`)
    if (!home.contentType.includes('text/html')) fail(`Home content-type was ${home.contentType}`)
    if (!home.text.includes('Knead') || !home.text.includes('static/product-shell-runtime.js')) {
      fail('Home page did not contain Knead shell markers')
    }

    const shell = await getText(`${baseUrl}/static/product-shell-runtime.js`)
    if (!shell.text.includes('function _creatorDraftInstruction')) {
      fail('product-shell-runtime.js did not contain Creator runtime code')
    }

    const products = await getJson(`${baseUrl}/api/products`)
    const ids = new Set((products.products || []).map((item) => item.id))
    for (const id of builtinProductIds) {
      if (!ids.has(id)) fail(`Missing built-in product from /api/products: ${id}`)
    }

    const draftCreate = await postJson(`${baseUrl}/api/product-drafts/create`, {
      title: 'Smoke Timer',
      prompt: 'A tiny focus timer that can stay as a simple chat AI.',
    })
    const draft = draftCreate && draftCreate.draft
    if (!draft || !draft.id || !draft.workspace_path || !draft.manifest_path) {
      fail(`Creator draft create returned an invalid payload: ${JSON.stringify(draftCreate)}`)
    }
    if (ids.has(draft.id)) fail('Creator draft unexpectedly appeared in the initial product registry')

    const draftManifest = JSON.parse(readFileSync(draft.manifest_path, 'utf8'))
    Object.assign(draftManifest, {
      title: 'Smoke Timer',
      desc: 'A tiny focus timer AI for release smoke checks.',
      placeholder: 'Tell Smoke Timer what focus session you want...',
      suggestions: [
        ['Start a 25 minute focus session.', 'Start focus'],
        ['Help me plan three focus rounds.', 'Plan rounds'],
      ],
      draft_status: 'ready',
      draft_ready_reason: 'Smoke test shaped a minimal chat-only AI.',
      ui_mode: 'chat_only',
      product_layout: 'chat_only',
      updated_at: '2026-06-23T00:00:00Z',
    })
    writeFileSync(draft.manifest_path, `${JSON.stringify(draftManifest, null, 2)}\n`, 'utf8')

    const draftStatus = await postJson(`${baseUrl}/api/product-drafts/status`, {
      workspace_path: draft.workspace_path,
    })
    if (!draftStatus.ready || draftStatus.published) {
      fail(`Creator draft status should be ready but unpublished: ${JSON.stringify(draftStatus)}`)
    }
    if (draftStatus.ready_reason !== 'Smoke test shaped a minimal chat-only AI.') {
      fail(`Creator draft status lost ready_reason: ${JSON.stringify(draftStatus)}`)
    }

    const published = await postJson(`${baseUrl}/api/product-drafts/publish`, {
      workspace_path: draft.workspace_path,
      if_ready: true,
    })
    const publishedProduct = published && published.product
    if (!published.published || !publishedProduct || !publishedProduct.id) {
      fail(`Creator draft publish returned an invalid payload: ${JSON.stringify(published)}`)
    }
    if (published.ready_reason !== 'Smoke test shaped a minimal chat-only AI.') {
      fail(`Creator draft publish lost ready_reason: ${JSON.stringify(published)}`)
    }
    const expectedRuntimeProductPath = realpathSync(join(runtimeProducts, publishedProduct.id))
    if (realpathSync(publishedProduct.workspace_path) !== expectedRuntimeProductPath) {
      fail(`Published product escaped runtime products dir: ${publishedProduct.workspace_path}`)
    }
    if (existsSync(join(repoRoot, 'products', publishedProduct.id))) {
      fail(`Published smoke product was written into repo products/: ${publishedProduct.id}`)
    }

    const afterPublish = await getJson(`${baseUrl}/api/products`)
    const publishedFromRegistry = (afterPublish.products || []).find((item) => item.id === publishedProduct.id)
    if (!publishedFromRegistry) fail('Published Creator product did not appear in /api/products')
    if (
      publishedFromRegistry.title !== 'Smoke Timer' ||
      publishedFromRegistry.ui_mode !== 'chat_only' ||
      publishedFromRegistry.product_layout !== 'chat_only' ||
      publishedFromRegistry.ui_status !== 'ready'
    ) {
      fail(`Published Creator product registry payload was wrong: ${JSON.stringify(publishedFromRegistry)}`)
    }

    console.log(`WebUI smoke passed at ${baseUrl}`)
  } finally {
    proc.kill('SIGTERM')
    await new Promise((resolve) => {
      const timer = setTimeout(resolve, 1500)
      proc.once('exit', () => {
        clearTimeout(timer)
        resolve()
      })
    })
    rmSync(stateRoot, { recursive: true, force: true })
    if (process.exitCode && output) {
      console.error(output)
    }
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error))
  process.exit(1)
})
