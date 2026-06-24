#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { basename, dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const productRoot = join(repoRoot, 'products')
const productSchemaId = 'https://knead.dev/schemas/product.schema.json'
const productCatalogSchemaId = 'https://knead.dev/schemas/product-catalog.schema.json'
const productSchemaFile = 'product.schema.json'
const productCatalogSchemaFile = 'product-catalog.schema.json'
const productCatalogFile = 'catalog.json'
const allowedLayouts = new Set(['chat_only', 'chat_center', 'chat_left_canvas_right', 'canvas_full'])
const allowedUiModes = new Set(['chat_only', 'workspace'])
const forbiddenSecretKeys = /(?:api[_-]?key|secret|token|password|credential|private[_-]?key|fal[_-]?key)/i
const forbiddenLocalText = /(?:\/Users\/|\.hermes-home|node_modules|products\/[^/]+\/(?:outputs|versions)\/)/
const forbiddenSourceNames = new Set([
  '.DS_Store',
  '.env',
  '.knead-published.json',
  '.venv',
  '__pycache__',
  'outputs',
  'state.json',
  'versions',
])
const creditedAssetExtensions = new Set(['.avif', '.gif', '.jpeg', '.jpg', '.mp3', '.mp4', '.ogg', '.png', '.svg', '.webp', '.wav'])
const allowedManifestFields = new Set([
  '$schema',
  'id',
  'kind',
  'title',
  'avatar',
  'desc',
  'placeholder',
  'suggestions',
  'source_prompt',
  'system_prompt',
  'instructions',
  'product_type',
  'ui_mode',
  'product_layout',
  'canvas_label',
  'preview_entry',
  'ui_status',
  'skills',
  'tools',
  'updated_at',
  'metadata',
  'config',
])
const forbiddenRuntimeManifestFields = new Set(['draft', 'draft_status', 'draftStatus'])
const args = process.argv.slice(2)

let failed = false

function fail(message) {
  console.error(message)
  failed = true
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch (error) {
    fail(`Invalid JSON: ${path}\n  ${error instanceof Error ? error.message : String(error)}`)
    return null
  }
}

function readBuiltinCatalog() {
  const catalogPath = join(productRoot, productCatalogFile)
  const catalog = readJson(catalogPath)
  if (!catalog) return []
  if (catalog.$schema !== productCatalogSchemaId) {
    fail(`products/${productCatalogFile}.$schema must be ${productCatalogSchemaId}`)
  }
  if (!Array.isArray(catalog.builtins)) {
    fail(`products/${productCatalogFile}.builtins must be an array`)
    return []
  }
  const ids = []
  const seen = new Set()
  for (const [index, item] of catalog.builtins.entries()) {
    const label = `products/${productCatalogFile}.builtins[${index}]`
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      fail(`${label} must be an object`)
      continue
    }
    assertString(item.id, `${label}.id`)
    assertString(item.title, `${label}.title`)
    assertString(item.summary, `${label}.summary`)
    if (typeof item.id === 'string' && item.id.trim()) {
      if (seen.has(item.id)) {
        fail(`${label}.id is duplicated: ${item.id}`)
      }
      seen.add(item.id)
      ids.push(item.id)
    }
  }
  return ids
}

function assertString(value, label, { allowEmpty = false } = {}) {
  if (typeof value !== 'string') {
    fail(`${label} must be a string`)
    return
  }
  if (!allowEmpty && !value.trim()) {
    fail(`${label} must not be empty`)
  }
}

function assertStringArray(value, label) {
  if (!Array.isArray(value)) {
    fail(`${label} must be an array`)
    return
  }
  for (const item of value) {
    if (typeof item !== 'string' || !item.trim()) {
      fail(`${label} items must be non-empty strings`)
      break
    }
  }
}

function assertSuggestions(value, label) {
  if (!Array.isArray(value) || value.length === 0) {
    fail(`${label} must be a non-empty array`)
    return
  }
  for (const item of value) {
    if (
      !Array.isArray(item) ||
      item.length !== 2 ||
      typeof item[0] !== 'string' ||
      typeof item[1] !== 'string' ||
      !item[0].trim() ||
      !item[1].trim()
    ) {
      fail(`${label} items must be [prompt, label] string pairs`)
      break
    }
  }
}

function walkStrings(value, path, visitor) {
  if (typeof value === 'string') {
    visitor(value, path)
    return
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => walkStrings(item, `${path}[${index}]`, visitor))
    return
  }
  if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      if (forbiddenSecretKeys.test(key)) {
        fail(`${path}.${key} looks like a secret field and must not be in product.json`)
      }
      walkStrings(item, `${path}.${key}`, visitor)
    }
  }
}

function scanSourceTree(dir, label) {
  if (!existsSync(dir)) return
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    const display = relative(process.cwd(), path) || path
    if (
      forbiddenSourceNames.has(entry.name) ||
      entry.name.endsWith('.pptx') ||
      entry.name.endsWith('.lock') ||
      entry.name.startsWith('hermes_intro.')
    ) {
      fail(`${label} contains runtime/local artifact: ${display}`)
      continue
    }
    if (entry.isDirectory()) scanSourceTree(path, label)
  }
}

function hasCreditedAssets(dir) {
  if (!existsSync(dir)) return false
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (hasCreditedAssets(path)) return true
      continue
    }
    const lower = entry.name.toLowerCase()
    for (const ext of creditedAssetExtensions) {
      if (lower.endsWith(ext)) return true
    }
  }
  return false
}

function assertAssetCredits(dir, label) {
  const assetsDir = join(dir, 'assets')
  if (!hasCreditedAssets(assetsDir)) return
  const creditsPath = join(assetsDir, 'CREDITS.md')
  if (!existsSync(creditsPath)) {
    fail(`${label} contains credited assets but is missing assets/CREDITS.md`)
    return
  }
  const credits = readFileSync(creditsPath, 'utf8')
  for (const phrase of ['Source:', 'License:']) {
    if (!credits.includes(phrase)) {
      fail(`${label}/assets/CREDITS.md must mention ${phrase}`)
    }
  }
}

function assertProductSchemaContract(schema) {
  const serialized = JSON.stringify(schema)
  const requiredFields = [
    '$schema',
    'id',
    'kind',
    'title',
    'avatar',
    'desc',
    'placeholder',
    'suggestions',
    'source_prompt',
    'product_type',
    'ui_mode',
    'product_layout',
    'preview_entry',
    'ui_status',
    'skills',
    'tools',
    'updated_at',
  ]

  for (const field of requiredFields) {
    if (!Array.isArray(schema.required) || !schema.required.includes(field)) {
      fail(`products/${productSchemaFile} must require ${field}`)
    }
  }

  if (schema.additionalProperties !== false) {
    fail(`products/${productSchemaFile} must set additionalProperties=false at the top level`)
  }
  if (!schema.properties?.metadata || schema.properties.metadata.additionalProperties !== true) {
    fail(`products/${productSchemaFile} must expose metadata as the explicit extension slot`)
  }
  if (!schema.properties?.config || schema.properties.config.additionalProperties !== true) {
    fail(`products/${productSchemaFile} must expose config as the explicit extension slot`)
  }

  for (const layout of allowedLayouts) {
    if (!serialized.includes(layout)) {
      fail(`products/${productSchemaFile} must document product_layout ${layout}`)
    }
  }
  for (const mode of allowedUiModes) {
    if (!serialized.includes(mode)) {
      fail(`products/${productSchemaFile} must document ui_mode ${mode}`)
    }
  }
  for (const draftField of ['draft', 'draft_status', 'draftStatus']) {
    if (!serialized.includes(draftField)) {
      fail(`products/${productSchemaFile} must reject runtime draft field ${draftField}`)
    }
  }
  if (!serialized.includes('canvas_label') || !serialized.includes('minLength')) {
    fail(`products/${productSchemaFile} must require canvas_label for workspace layouts`)
  }
}

function verifyProduct(id, options = {}) {
  const dir = options.dir || join(productRoot, id)
  const manifestPath = join(dir, 'product.json')
  const readmePath = join(dir, 'README.md')
  const label = options.label || `products/${id}`
  if (!existsSync(dir)) return fail(`Missing product directory: ${label}`)
  if (!existsSync(readmePath)) {
    fail(`Missing README for product: ${label}/README.md`)
  } else {
    const readme = readFileSync(readmePath, 'utf8')
    if (!readme.includes('## Product Shape')) {
      fail(`${label}/README.md must include a "## Product Shape" section explaining why this is a maintained example`)
    }
  }
  if (!existsSync(manifestPath)) return fail(`Missing product manifest: ${label}/product.json`)
  if (options.requireCleanSource) scanSourceTree(dir, label)
  if (options.requireCleanSource) assertAssetCredits(dir, label)

  const manifest = readJson(manifestPath)
  if (!manifest) return

  if (manifest.id !== id) fail(`${label}/product.json id must match directory name`)
  for (const field of Object.keys(manifest)) {
    if (forbiddenRuntimeManifestFields.has(field)) {
      fail(`${label} must be a curated built-in product, not a draft`)
      continue
    }
    if (!allowedManifestFields.has(field)) {
      fail(`${label}.${field} is not part of the public product manifest contract`)
    }
  }
  if (manifest.$schema !== productSchemaId) fail(`${label}.$schema must be ${productSchemaId}`)
  assertString(manifest.kind, `${label}.kind`)
  assertString(manifest.title, `${label}.title`)
  assertString(manifest.avatar, `${label}.avatar`)
  assertString(manifest.desc, `${label}.desc`)
  assertString(manifest.placeholder, `${label}.placeholder`)
  assertString(manifest.source_prompt, `${label}.source_prompt`)
  assertString(manifest.product_type, `${label}.product_type`)
  assertString(manifest.preview_entry, `${label}.preview_entry`)
  assertString(manifest.ui_status, `${label}.ui_status`)
  assertString(manifest.updated_at, `${label}.updated_at`)
  assertSuggestions(manifest.suggestions, `${label}.suggestions`)
  assertStringArray(manifest.skills, `${label}.skills`)
  assertStringArray(manifest.tools, `${label}.tools`)

  if (!allowedUiModes.has(manifest.ui_mode)) {
    fail(`${label}.ui_mode must be one of ${Array.from(allowedUiModes).join(', ')}`)
  }
  if (!allowedLayouts.has(manifest.product_layout)) {
    fail(`${label}.product_layout must be one of ${Array.from(allowedLayouts).join(', ')}`)
  }
  if (manifest.ui_mode === 'chat_only' && manifest.product_layout !== 'chat_only') {
    fail(`${label} uses ui_mode=chat_only but product_layout is not chat_only`)
  }
  if (manifest.product_layout === 'chat_only' && manifest.ui_mode !== 'chat_only') {
    fail(`${label} uses product_layout=chat_only but ui_mode is not chat_only`)
  }
  if (manifest.product_layout !== 'chat_only' && !manifest.canvas_label) {
    fail(`${label}.canvas_label is required for workspace layouts`)
  }
  const preview = join(dir, manifest.preview_entry || '')
  if (!existsSync(preview)) {
    fail(`${label}.preview_entry does not exist: ${manifest.preview_entry}`)
  }

  walkStrings(manifest, label, (text, path) => {
    if (forbiddenLocalText.test(text)) {
      fail(`${path} contains local/runtime path text: ${text}`)
    }
  })
}

function verifyBuiltins() {
  if (!existsSync(join(productRoot, productSchemaFile))) fail(`Missing product schema: products/${productSchemaFile}`)
  if (!existsSync(join(productRoot, productCatalogSchemaFile))) fail(`Missing product catalog schema: products/${productCatalogSchemaFile}`)
  if (!existsSync(join(productRoot, productCatalogFile))) fail(`Missing product catalog: products/${productCatalogFile}`)

  const productSchema = readJson(join(productRoot, productSchemaFile))
  if (productSchema && productSchema.$id !== productSchemaId) {
    fail(`products/${productSchemaFile}.$id must be ${productSchemaId}`)
  }
  if (productSchema) assertProductSchemaContract(productSchema)
  const productCatalogSchema = readJson(join(productRoot, productCatalogSchemaFile))
  if (productCatalogSchema && productCatalogSchema.$id !== productCatalogSchemaId) {
    fail(`products/${productCatalogSchemaFile}.$id must be ${productCatalogSchemaId}`)
  }

  const builtins = readBuiltinCatalog()
  for (const id of builtins) {
    verifyProduct(id, { requireCleanSource: true })
  }

  for (const entry of readdirSync(productRoot, { withFileTypes: true })) {
    if (entry.name === 'README.md' || entry.name === productSchemaFile || entry.name === productCatalogFile || entry.name.startsWith('.')) continue
    if (entry.isDirectory() && !builtins.includes(entry.name)) {
      fail(`Unexpected product directory under products/: ${entry.name}`)
    }
  }
}

function verifyCandidates(paths) {
  paths = paths.filter((item) => item !== '--')
  if (!paths.length) {
    fail('Usage: node scripts/verify-products.mjs --candidate <product-dir> [more-product-dirs...]')
    return
  }
  for (const rawPath of paths) {
    const dir = resolve(rawPath)
    const id = basename(dir)
    verifyProduct(id, {
      dir,
      label: rawPath,
      requireCleanSource: true,
    })
  }
}

const candidateIndex = args.indexOf('--candidate')
if (candidateIndex >= 0) {
  verifyCandidates(args.slice(candidateIndex + 1))
} else {
  verifyBuiltins()
}

if (failed) {
  process.exit(1)
}

if (candidateIndex >= 0) {
  const candidateCount = args.slice(candidateIndex + 1).filter((item) => item !== '--').length
  console.log(`Verified ${candidateCount} candidate product${candidateCount === 1 ? '' : 's'}`)
} else {
  console.log(`Verified ${readBuiltinCatalog().length} built-in product manifests`)
}
