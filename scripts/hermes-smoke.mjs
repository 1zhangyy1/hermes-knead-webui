#!/usr/bin/env node

const gatewayUrl = trimTrailingSlash(
  process.env.HERMES_API_URL || 'http://127.0.0.1:8642',
)
const dashboardUrl = trimTrailingSlash(
  process.env.HERMES_DASHBOARD_URL || 'http://127.0.0.1:9119',
)
const apiToken = process.env.HERMES_API_TOKEN || process.env.API_SERVER_KEY || ''
const skipAgentRuns = truthy(process.env.HERMES_SMOKE_SKIP_AGENT_RUNS)

function trimTrailingSlash(value) {
  return String(value || '').replace(/\/+$/, '')
}

function truthy(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').toLowerCase())
}

function headers(extra = {}) {
  return {
    ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}),
    ...extra,
  }
}

function short(value, max = 700) {
  const text =
    typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max)}...` : text
}

async function readResponse(res) {
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return await res.json()
  }
  return await res.text()
}

async function check(name, fn) {
  const started = Date.now()
  try {
    const result = await fn()
    const elapsed = Date.now() - started
    console.log(`PASS ${name} (${elapsed}ms)`)
    if (result !== undefined) console.log(indent(short(result)))
    return { name, ok: true, result }
  } catch (error) {
    const elapsed = Date.now() - started
    console.log(`FAIL ${name} (${elapsed}ms)`)
    console.log(indent(error instanceof Error ? error.message : String(error)))
    return { name, ok: false, error: String(error) }
  }
}

function indent(text) {
  return String(text)
    .split('\n')
    .map((line) => `  ${line}`)
    .join('\n')
}

async function getJson(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: headers(opts.headers || {}),
  })
  const body = await readResponse(res)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}\n${short(body)}`)
  }
  return body
}

async function postJson(url, body, opts = {}) {
  const res = await fetch(url, {
    method: 'POST',
    ...opts,
    headers: headers({
      'content-type': 'application/json',
      ...(opts.headers || {}),
    }),
    body: JSON.stringify(body),
  })
  const payload = await readResponse(res)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}\n${short(payload)}`)
  }
  return payload
}

async function streamSse(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: headers({
      accept: 'text/event-stream',
      ...(opts.headers || {}),
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}\n${short(body)}`)
  }
  if (!res.body) throw new Error('Missing response body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const events = []
  const deadline = Date.now() + Number(process.env.HERMES_SMOKE_STREAM_MS || 60000)

  while (Date.now() < deadline) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const raw = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = parseSseEvent(raw)
      if (event) {
        events.push(event)
        if (
          event.event === 'run.completed' ||
          event.event === 'run.failed' ||
          event.event === 'response.completed' ||
          event.event === 'response.failed' ||
          event.data?.event === 'run.completed' ||
          event.data?.event === 'run.failed'
        ) {
          try {
            await reader.cancel()
          } catch {}
          return events
        }
      }
      boundary = buffer.indexOf('\n\n')
    }
  }

  try {
    await reader.cancel()
  } catch {}
  return events
}

function parseSseEvent(raw) {
  const lines = raw.split('\n')
  let event = ''
  const dataLines = []
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!event && dataLines.length === 0) return null
  const dataText = dataLines.join('\n')
  let data = dataText
  if (dataText && dataText !== '[DONE]') {
    try {
      data = JSON.parse(dataText)
    } catch {}
  }
  return { event, data }
}

async function smokeResponses() {
  const payload = await postJson(`${gatewayUrl}/v1/responses`, {
    input: 'Reply with exactly: hermes smoke ok',
    stream: false,
    store: false,
  })
  return payload
}

async function smokeRun() {
  const created = await postJson(`${gatewayUrl}/v1/runs`, {
    input: 'Reply with exactly: hermes run smoke ok',
    session_id: `space-smoke-${Date.now()}`,
  })
  const runId = created.run_id
  if (!runId) throw new Error(`No run_id in response: ${short(created)}`)
  const events = await streamSse(`${gatewayUrl}/v1/runs/${runId}/events`)
  return {
    created,
    events: events.map((event) => ({
      event: event.event || event.data?.event || 'message',
      data: event.data,
    })),
  }
}

console.log('Hermes smoke')
console.log(`  gateway:   ${gatewayUrl}`)
console.log(`  dashboard: ${dashboardUrl}`)
console.log(`  token:     ${apiToken ? 'set' : 'not set'}`)
console.log('')

const results = []

results.push(await check('gateway /health', () => getJson(`${gatewayUrl}/health`)))
results.push(
  await check('gateway /v1/capabilities', () =>
    getJson(`${gatewayUrl}/v1/capabilities`),
  ),
)
results.push(
  await check('dashboard /api/status', () =>
    getJson(`${dashboardUrl}/api/status`),
  ),
)

if (skipAgentRuns) {
  console.log('SKIP agent runs (HERMES_SMOKE_SKIP_AGENT_RUNS is set)')
} else {
  results.push(await check('responses API', smokeResponses))
  results.push(await check('runs API + SSE events', smokeRun))
}

const failed = results.filter((result) => !result.ok)
console.log('')
console.log(
  failed.length === 0
    ? `All ${results.length} checks passed.`
    : `${failed.length}/${results.length} checks failed.`,
)
process.exitCode = failed.length === 0 ? 0 : 1
