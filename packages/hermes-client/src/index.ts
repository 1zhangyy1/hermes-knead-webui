export type HermesRunEvent = {
  event: string
  data?: Record<string, unknown>
}

export type HermesRunStreamResult = 'completed' | 'failed'

export type HermesRunCreateInput = {
  input: string
  sessionId?: string
}

export type HermesRunCreated = {
  runId: string
  status?: string
}

export type HermesResponseCreateInput = {
  input: string
  store?: boolean
}

export type HermesClientOptions = {
  gatewayBaseUrl?: string
  dashboardBaseUrl?: string
}

export type HermesClient = ReturnType<typeof createHermesClient>

const defaultRunEventNames = [
  'message.delta',
  'message.completed',
  'reasoning.available',
  'tool.started',
  'tool.progress',
  'tool.completed',
  'approval.required',
  'run.completed',
  'run.failed',
]

export function createHermesClient(options: HermesClientOptions = {}) {
  const gatewayBaseUrl = trimTrailingSlash(options.gatewayBaseUrl ?? '/hermes')
  const dashboardBaseUrl = trimTrailingSlash(
    options.dashboardBaseUrl ?? '/hermes-dashboard',
  )

  return {
    gatewayBaseUrl,
    dashboardBaseUrl,
    gateway: {
      health: () => getJson(`${gatewayBaseUrl}/health`, 'Hermes gateway health'),
      capabilities: () =>
        getJson(`${gatewayBaseUrl}/v1/capabilities`, 'Hermes gateway capabilities'),
    },
    dashboard: {
      status: () =>
        getJson(`${dashboardBaseUrl}/api/status`, 'Hermes dashboard status'),
    },
    responses: {
      createText: (input: HermesResponseCreateInput) =>
        createResponseText(`${gatewayBaseUrl}/v1/responses`, input),
    },
    runs: {
      create: (input: HermesRunCreateInput) =>
        createRun(`${gatewayBaseUrl}/v1/runs`, input),
      streamEvents: (runId: string, onEvent: (event: HermesRunEvent) => void) =>
        streamRunEvents(`${gatewayBaseUrl}/v1/runs/${runId}/events`, onEvent),
    },
  }
}

async function createResponseText(
  url: string,
  input: HermesResponseCreateInput,
): Promise<string> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      input: input.input,
      stream: false,
      store: input.store ?? false,
    }),
  })

  if (!res.ok) {
    throw new Error(await readFailure(res, 'Hermes response request'))
  }

  const payload = (await res.json()) as {
    output?: Array<{
      content?: Array<{ text?: string; type?: string }>
      role?: string
      type?: string
    }>
    output_text?: string
  }

  if (typeof payload.output_text === 'string') return payload.output_text

  const text = payload.output
    ?.flatMap((item) => item.content ?? [])
    .map((content) => content.text ?? '')
    .join('')
    .trim()

  return text || ''
}

async function getJson(url: string, label: string): Promise<unknown> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(await readFailure(res, label))
  }
  return res.json()
}

async function createRun(
  url: string,
  input: HermesRunCreateInput,
): Promise<HermesRunCreated> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      input: input.input,
      ...(input.sessionId ? { session_id: input.sessionId } : {}),
    }),
  })

  if (!res.ok) {
    throw new Error(await readFailure(res, 'Hermes run request'))
  }

  const created = (await res.json()) as { run_id?: string; status?: string }
  if (!created.run_id) throw new Error('Hermes did not return a run_id')

  return {
    runId: created.run_id,
    status: created.status,
  }
}

async function streamRunEvents(
  url: string,
  onEvent: (event: HermesRunEvent) => void,
): Promise<HermesRunStreamResult> {
  if (typeof EventSource !== 'undefined') {
    return streamRunEventsWithEventSource(url, onEvent)
  }

  return streamRunEventsWithFetch(url, onEvent)
}

function streamRunEventsWithEventSource(
  url: string,
  onEvent: (event: HermesRunEvent) => void,
): Promise<HermesRunStreamResult> {
  return new Promise((resolve, reject) => {
    const source = new EventSource(url)
    let settled = false

    const finish = (status: HermesRunStreamResult) => {
      if (settled) return
      settled = true
      source.close()
      resolve(status)
    }

    const handle = (event: MessageEvent, fallbackEvent: string) => {
      const parsed = parseEventData(event.data)
      const runEvent = {
        event:
          fallbackEvent || (typeof parsed?.event === 'string' ? parsed.event : 'message'),
        data: parsed,
      }
      onEvent(runEvent)
      if (runEvent.event === 'run.completed') finish('completed')
      if (runEvent.event === 'run.failed') finish('failed')
    }

    for (const eventName of defaultRunEventNames) {
      source.addEventListener(eventName, (event) => handle(event, eventName))
    }

    source.onmessage = (event) => handle(event, '')
    source.onerror = () => {
      if (settled) return
      settled = true
      source.close()
      reject(new Error('Hermes event stream closed before the run completed'))
    }
  })
}

async function streamRunEventsWithFetch(
  url: string,
  onEvent: (event: HermesRunEvent) => void,
): Promise<HermesRunStreamResult> {
  const res = await fetch(url, {
    headers: { accept: 'text/event-stream' },
  })
  if (!res.ok) throw new Error(await readFailure(res, 'Hermes run event stream'))
  if (!res.body) throw new Error('Hermes run stream had no body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const raw = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = parseSse(raw)
      if (event) {
        onEvent(event)
        if (event.event === 'run.completed' || event.event === 'run.failed') {
          try {
            await reader.cancel()
          } catch {
            // The stream is already closing; nothing useful to recover here.
          }
          return event.event === 'run.failed' ? 'failed' : 'completed'
        }
      }
      boundary = buffer.indexOf('\n\n')
    }
  }

  return 'failed'
}

function parseSse(raw: string): HermesRunEvent | null {
  const dataLines: string[] = []
  let event = ''
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!event && dataLines.length === 0) return null
  const dataText = dataLines.join('\n')
  const data = parseEventData(dataText)
  if (data) event = event || (typeof data.event === 'string' ? data.event : '')
  return { event: event || 'message', data }
}

function parseEventData(dataText: string): Record<string, unknown> | undefined {
  if (!dataText || dataText === '[DONE]') return undefined
  try {
    return JSON.parse(dataText) as Record<string, unknown>
  } catch {
    return { text: dataText }
  }
}

async function readFailure(res: Response, label: string): Promise<string> {
  const body = await res.text().catch(() => '')
  return `${label} failed (${res.status}): ${body || res.statusText || 'empty response'}`
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}
