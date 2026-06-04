import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { createHermesClient, type HermesRunEvent } from '@ai-space/hermes-client'
import {
  Activity,
  Bot,
  Brush,
  Check,
  Eye,
  FileText,
  Loader2,
  MessageSquareText,
  PanelRight,
  Play,
  Presentation,
  RotateCcw,
  Sparkles,
  WandSparkles,
} from 'lucide-react'

type Slide = {
  id: string
  title: string
  body: string
}

type EvolutionProposal = {
  id: string
  title: string
  summary: string
  changes: string[]
  patchPreview: string
  rationale: string
}

export type PptStudioProps = {
  agentInstructions: string
  gatewayOnline: boolean
}

const hermes = createHermesClient()
const evolutionStorageKey = 'ai-space:ppt-studio:applied-evolution'
const initialNotes =
  'Keep the first pass focused on narrative structure. Visual polish comes after the story is sharp.'

const initialSlides: Slide[] = [
  {
    id: '01',
    title: 'Opening',
    body: 'What the audience should believe in the first minute.',
  },
  {
    id: '02',
    title: 'Problem',
    body: 'The current pain, stakes, and why now matters.',
  },
  {
    id: '03',
    title: 'Solution',
    body: 'The product promise and why this approach is different.',
  },
]

const investorProposal: EvolutionProposal = {
  id: 'investor-mode-v0',
  title: 'Add Investor Pitch Mode',
  summary:
    'Adapt PPT Studio for fundraising work by adding an investor Q&A panel, metrics prompts, and a sharper deck review loop.',
  changes: [
    'Add an Investor Q&A panel to rehearse objections and partner questions.',
    'Bias the workspace toward traction, metrics, moat, ask, and risk slides.',
    'Persist the applied evolution locally so the Space keeps its new shape after refresh.',
  ],
  patchPreview: [
    'spaces/ppt-studio/src/index.tsx',
    '+ evolution proposal state',
    '+ preview/apply/rollback controls',
    '+ investor Q&A panel when evolution is previewed or applied',
    '+ localStorage persistence for applied variant',
  ].join('\n'),
  rationale:
    'The current prompt and generated deck content are already investor-oriented, so the workspace should expose investor-review affordances directly instead of hiding them in generic notes.',
}

export function PptStudio({ agentInstructions, gatewayOnline }: PptStudioProps) {
  const [slides, setSlides] = useState(initialSlides)
  const [selectedSlideId, setSelectedSlideId] = useState('01')
  const [notes, setNotes] = useState(initialNotes)
  const [brandVoice, setBrandVoice] = useState('Precise, warm, investor-ready')
  const [agentText, setAgentText] = useState('')
  const [runEvents, setRunEvents] = useState<HermesRunEvent[]>([])
  const [agentStatus, setAgentStatus] = useState('Idle')
  const [input, setInput] = useState(
    'Create a 6-slide pitch deck outline for an AI product that evolves its own workspace.',
  )
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState('')
  const [proposal, setProposal] = useState<EvolutionProposal | null>(() =>
    readAppliedEvolution() === investorProposal.id ? investorProposal : null,
  )
  const [isProposingEvolution, setIsProposingEvolution] = useState(false)
  const [isPreviewingEvolution, setIsPreviewingEvolution] = useState(false)
  const [appliedEvolution, setAppliedEvolution] = useState(() => readAppliedEvolution())
  const [evolutionError, setEvolutionError] = useState('')

  const selectedSlide = slides.find((slide) => slide.id === selectedSlideId) ?? slides[0]
  const investorModeActive = isPreviewingEvolution || appliedEvolution === investorProposal.id

  const deckBrief = useMemo(
    () => ({
      selectedSlide,
      slideCount: slides.length,
      brandVoice,
      notes,
      activeEvolution: investorModeActive ? investorProposal.id : 'none',
    }),
    [brandVoice, investorModeActive, notes, selectedSlide, slides.length],
  )

  const runAgent = useCallback(() => {
    if (!input.trim() || isRunning) return
    setIsRunning(true)
    setError('')
    setAgentText('')
    setRunEvents([])
    setAgentStatus('Creating run')

    void (async () => {
      try {
        const created = await hermes.runs.create({
          sessionId: `ppt-studio-${Date.now()}`,
          input: [
            agentInstructions,
            '',
            input.trim(),
            '',
            `Current PPT Studio state:\n${JSON.stringify(deckBrief, null, 2)}`,
          ].join('\n'),
        })
        setAgentStatus('Streaming')

        const streamResult = await hermes.runs.streamEvents(created.runId, (event) => {
          setRunEvents((events) => [...events, event])
          const delta = typeof event.data?.delta === 'string' ? event.data.delta : ''
          if (delta) setAgentText((text) => `${text}${delta}`)
          if (event.data?.output && typeof event.data.output === 'string') {
            setAgentText(event.data.output)
          }
          if (event.event === 'run.failed') {
            const message =
              typeof event.data?.error === 'string' ? event.data.error : 'Hermes run failed'
            setError(message)
          }
        })
        setAgentStatus(streamResult === 'failed' ? 'Failed' : 'Complete')
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        setError(message || 'Hermes run failed before returning an error message')
        setAgentStatus('Failed')
      } finally {
        setIsRunning(false)
      }
    })()
  }, [agentInstructions, deckBrief, input, isRunning])

  const proposeEvolution = useCallback(() => {
    if (isProposingEvolution) return
    setIsProposingEvolution(true)
    setEvolutionError('')
    setProposal(null)

    void (async () => {
      let rationale = investorProposal.rationale
      try {
        if (gatewayOnline) {
          const created = await hermes.runs.create({
            sessionId: `ppt-evolution-${Date.now()}`,
            input: [
              'You are improving PPT Studio as an AI Space.',
              'Return a concise rationale for one UI evolution that helps this user make investor pitch decks.',
              'Do not include code. Keep it under 90 words.',
              '',
              `Current PPT Studio state:\n${JSON.stringify(deckBrief, null, 2)}`,
            ].join('\n'),
          })
          let streamed = ''
          await hermes.runs.streamEvents(created.runId, (event) => {
            const delta = typeof event.data?.delta === 'string' ? event.data.delta : ''
            streamed += delta
          })
          if (streamed.trim()) rationale = streamed.trim()
        }
      } catch (err) {
        setEvolutionError(
          err instanceof Error
            ? `Hermes proposal fallback used: ${err.message}`
            : 'Hermes proposal fallback used.',
        )
      } finally {
        setProposal({ ...investorProposal, rationale })
        setIsPreviewingEvolution(false)
        setIsProposingEvolution(false)
      }
    })()
  }, [deckBrief, gatewayOnline, isProposingEvolution])

  const previewEvolution = useCallback(() => {
    if (!proposal) return
    setIsPreviewingEvolution(true)
  }, [proposal])

  const applyEvolution = useCallback(() => {
    if (!proposal) return
    setAppliedEvolution(proposal.id)
    setIsPreviewingEvolution(false)
    setNotes('Investor Pitch Mode is applied. Use Q&A and metrics prompts before polishing visuals.')
    window.localStorage.setItem(evolutionStorageKey, proposal.id)
  }, [proposal])

  const rollbackEvolution = useCallback(() => {
    setAppliedEvolution('')
    setIsPreviewingEvolution(false)
    setNotes(initialNotes)
    window.localStorage.removeItem(evolutionStorageKey)
  }, [])

  useEffect(() => {
    if (!agentText.trim()) return
    const parsed = extractSlides(agentText)
    if (parsed.length >= 3) {
      setSlides(parsed)
      setSelectedSlideId(parsed[0].id)
      setNotes('Agent output has been mapped into the current deck structure.')
    }
  }, [agentText])

  return (
    <div className="studio-grid">
      <section className="studio-main">
        <header className="studio-header">
          <div>
            <p className="eyebrow">Space: Presentation</p>
            <h1>{investorModeActive ? 'PPT Studio: Investor Mode' : 'PPT Studio'}</h1>
            <p className="studio-subtitle">
              {investorModeActive
                ? 'The workspace has evolved for fundraising decks, Q&A rehearsal, metrics, moat, and investor objections.'
                : 'A scene-specific workspace where Hermes helps the interface become presentation-shaped from the first turn.'}
            </p>
          </div>
          <button
            className="primary-action"
            disabled={!gatewayOnline || isRunning}
            onClick={runAgent}
            type="button"
          >
            {isRunning ? <Loader2 className="spin" size={17} /> : <Play size={17} />}
            Run Agent
          </button>
        </header>

        <div className="workspace-band">
          <Panel title="Outline" icon={<FileText size={18} />}>
            <div className="slide-list">
              {slides.map((slide) => (
                <button
                  className={`slide-row ${slide.id === selectedSlideId ? 'active' : ''}`}
                  key={slide.id}
                  onClick={() => setSelectedSlideId(slide.id)}
                  type="button"
                >
                  <span>{slide.id}</span>
                  <strong>{slide.title}</strong>
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Slide" icon={<Presentation size={18} />}>
            <div className="slide-canvas">
              <span>Slide {selectedSlide.id}</span>
              <h2>{selectedSlide.title}</h2>
              <p>{selectedSlide.body}</p>
            </div>
          </Panel>
        </div>

        <div className={`workspace-band compact ${investorModeActive ? 'evolved' : ''}`}>
          <Panel title="Brand Kit" icon={<Brush size={18} />}>
            <label className="field-label" htmlFor="brandVoice">
              Voice
            </label>
            <input
              id="brandVoice"
              value={brandVoice}
              onChange={(event) => setBrandVoice(event.target.value)}
            />
            <div className="swatches" aria-label="Brand colors">
              <span className="swatch coral" />
              <span className="swatch ink" />
              <span className="swatch mint" />
              <span className="swatch gold" />
            </div>
          </Panel>

          <Panel title="Speaker Notes" icon={<MessageSquareText size={18} />}>
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
          </Panel>

          <Panel title="Evolution" icon={<WandSparkles size={18} />}>
            <EvolutionPanel
              applied={appliedEvolution === investorProposal.id}
              error={evolutionError}
              isPreviewing={isPreviewingEvolution}
              isProposing={isProposingEvolution}
              onApply={applyEvolution}
              onPreview={previewEvolution}
              onPropose={proposeEvolution}
              onRollback={rollbackEvolution}
              proposal={proposal}
            />
          </Panel>

          {investorModeActive ? (
            <Panel title="Investor Q&A" icon={<Sparkles size={18} />}>
              <div className="qa-panel">
                <strong>Likely objections</strong>
                <span>Why now?</span>
                <span>What is defensible?</span>
                <span>How does usage compound?</span>
                <button
                  className="icon-text-button"
                  onClick={() =>
                    setInput(
                      'Generate 8 investor Q&A prompts for this deck, including traction, moat, market timing, and product risk.',
                    )
                  }
                  type="button"
                >
                  <Sparkles size={15} />
                  Draft Q&A
                </button>
              </div>
            </Panel>
          ) : null}
        </div>
      </section>

      <aside className="agent-panel">
        <div className="agent-panel-header">
          <div className="agent-avatar">
            <Bot size={20} />
          </div>
          <div>
            <h2>Hermes Agent</h2>
            <p>{gatewayOnline ? 'Connected to project runtime' : 'Gateway offline'}</p>
          </div>
        </div>

        <textarea
          className="agent-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
        <button
          className="primary-action wide"
          disabled={!gatewayOnline || isRunning}
          onClick={runAgent}
          type="button"
        >
          {isRunning ? <Loader2 className="spin" size={17} /> : <Sparkles size={17} />}
          {isRunning ? 'Thinking' : 'Send to Hermes'}
        </button>

        {error ? <div className="error-box">{error}</div> : null}

        <div className="agent-output">
          <div className="output-title">
            <Activity size={16} />
            Output
            <span className="agent-status">{agentStatus}</span>
          </div>
          <p>{agentText || 'Hermes output will appear here and can reshape the deck outline.'}</p>
        </div>

        <div className="event-log">
          <div className="output-title">
            <PanelRight size={16} />
            Events
          </div>
          {runEvents.slice(-8).map((event, index) => (
            <div className="event-row" key={`${event.event}-${index}`}>
              <span>{event.event || readEventName(event.data) || 'message'}</span>
            </div>
          ))}
        </div>
      </aside>
    </div>
  )
}

function EvolutionPanel({
  applied,
  error,
  isPreviewing,
  isProposing,
  onApply,
  onPreview,
  onPropose,
  onRollback,
  proposal,
}: {
  applied: boolean
  error: string
  isPreviewing: boolean
  isProposing: boolean
  onApply: () => void
  onPreview: () => void
  onPropose: () => void
  onRollback: () => void
  proposal: EvolutionProposal | null
}) {
  return (
    <div className="evolution-mvp">
      <div className="evolution-state">
        <span>{applied ? 'Applied' : isPreviewing ? 'Previewing' : proposal ? 'Proposed' : 'Ready'}</span>
      </div>

      {!proposal ? (
        <button className="primary-action wide" disabled={isProposing} onClick={onPropose} type="button">
          {isProposing ? <Loader2 className="spin" size={17} /> : <WandSparkles size={17} />}
          {isProposing ? 'Proposing' : 'Generate Evolution'}
        </button>
      ) : (
        <>
          <div className="evolution-proposal">
            <strong>{proposal.title}</strong>
            <p>{proposal.summary}</p>
            <div className="evolution-list">
              {proposal.changes.map((change) => (
                <span key={change}>{change}</span>
              ))}
            </div>
            <details>
              <summary>Patch preview</summary>
              <pre>{proposal.patchPreview}</pre>
            </details>
            <small>{proposal.rationale}</small>
          </div>
          <div className="evolution-actions">
            <button className="icon-text-button" disabled={applied} onClick={onPreview} type="button">
              <Eye size={15} />
              Preview
            </button>
            <button className="primary-action" disabled={applied} onClick={onApply} type="button">
              <Check size={15} />
              Apply
            </button>
            <button className="icon-text-button" disabled={!applied && !isPreviewing} onClick={onRollback} type="button">
              <RotateCcw size={15} />
              Rollback
            </button>
          </div>
        </>
      )}

      {error ? <div className="evolution-warning">{error}</div> : null}
    </div>
  )
}

function Panel({
  children,
  icon,
  title,
}: {
  children: ReactNode
  icon: ReactNode
  title: string
}) {
  return (
    <section className="panel">
      <div className="panel-title">
        {icon}
        <span>{title}</span>
      </div>
      {children}
    </section>
  )
}

function readAppliedEvolution(): string {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(evolutionStorageKey) ?? ''
}

function readEventName(data: Record<string, unknown> | undefined): string {
  return typeof data?.event === 'string' ? data.event : ''
}

function extractSlides(text: string): Slide[] {
  const lines = text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  const slides: Slide[] = []

  for (const line of lines) {
    const match = line.match(/^(?:slide\s*)?(\d+)[.)\-\s—:]+(.+)/i)
    if (!match) continue
    const [, number, rest] = match
    const [titleRaw, ...bodyParts] = rest.split(/[:—-]/)
    const title = titleRaw.trim()
    if (!title) continue
    slides.push({
      id: number.padStart(2, '0'),
      title,
      body: bodyParts.join(' - ').trim() || rest.trim(),
    })
  }

  return slides.slice(0, 8)
}
