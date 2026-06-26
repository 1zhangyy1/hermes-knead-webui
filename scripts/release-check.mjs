#!/usr/bin/env node

import { spawnSync } from 'node:child_process'

function truthy(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').toLowerCase())
}

const requireClean = process.argv.includes('--require-clean') || truthy(process.env.KNEAD_RELEASE_REQUIRE_CLEAN)
const DEFAULT_RELEASE_REPO_BASE = 'https://github.com/1zhangyy1/hermes-knead-webui'

function run(name, command, args, options = {}) {
  console.log(`\n==> ${name}`)
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    ...options,
  })
  if (result.status !== 0) {
    process.exitCode = result.status || 1
    throw new Error(`${name} failed`)
  }
}

function runCleanWorktreeCheck() {
  console.log('\n==> Git clean worktree check')
  const result = spawnSync('git', ['status', '--porcelain=v1'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'inherit'],
  })
  if (result.status !== 0) {
    process.exitCode = result.status || 1
    throw new Error('Git clean worktree check failed')
  }
  if (result.stdout.trim()) {
    process.exitCode = 1
    console.error(result.stdout.trimEnd())
    throw new Error('Git clean worktree check failed: commit, stash, or discard local changes before tagging.')
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

function releaseRepoBase() {
  const rawValue = process.env.KNEAD_RELEASE_REPOSITORY || process.env.KNEAD_RELEASE_REPO_URL
  if (!rawValue) return DEFAULT_RELEASE_REPO_BASE
  const base = githubRepoBaseFromUrl(rawValue)
  if (!base) {
    process.exitCode = 1
    throw new Error(`Release remote check failed: invalid release repository URL ${rawValue}`)
  }
  return base
}

function runReleaseRemoteCheck() {
  console.log('\n==> Git release remote check')
  const expectedBase = releaseRepoBase()
  const result = spawnSync('git', ['remote', 'get-url', 'origin'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'inherit'],
  })
  if (result.status !== 0) {
    process.exitCode = result.status || 1
    throw new Error('Git release remote check failed: missing origin remote.')
  }
  const actualBase = githubRepoBaseFromUrl(result.stdout.trim())
  if (actualBase !== expectedBase) {
    process.exitCode = 1
    throw new Error(`Git release remote check failed: origin is ${actualBase || result.stdout.trim()}, expected ${expectedBase}. Set KNEAD_RELEASE_REPO_URL if publishing elsewhere.`)
  }
}

try {
  if (requireClean) {
    runCleanWorktreeCheck()
    runReleaseRemoteCheck()
  }
  run('Git unstaged diff whitespace check', 'git', ['diff', '--check'])
  run('Git staged diff whitespace check', 'git', ['diff', '--cached', '--check'])
  run('Local product artifact check', 'node', ['scripts/clean-local-artifacts.mjs', '--check'])
  run('Release batch classification check', 'node', ['scripts/release-batches.mjs', '--check'])
  run('Frozen lockfile install check', 'pnpm', ['install', '--frozen-lockfile'])
  run('Default release gate: pnpm check', 'pnpm', ['check'])

  if (truthy(process.env.KNEAD_RELEASE_AGENT_SMOKE)) {
    run('Optional live Hermes agent smoke', 'node', ['scripts/hermes-smoke.mjs'])
  } else {
    console.log('\nSKIP optional live Hermes agent smoke')
    console.log('Set KNEAD_RELEASE_AGENT_SMOKE=1 after starting a configured Hermes Gateway to include it.')
  }

  console.log('\nRelease check passed')
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error))
  process.exit(process.exitCode || 1)
}
