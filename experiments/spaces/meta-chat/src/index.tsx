import { useState } from 'react'
import {
  Bot,
  CheckCircle2,
  ExternalLink,
  Eye,
  GitBranch,
  MonitorCog,
  PlusCircle,
  RefreshCcw,
  Sparkles,
} from 'lucide-react'

export type MetaChatProps = {
  hermesUiUrl?: string
  onCreateSpace?: (spaceId: string) => void
  onPreviewSpace?: (spaceId: string) => void
}

const defaultHermesUiUrl = 'http://127.0.0.1:3333/hermes-ui.html'
const growthStepStorageKey = 'ai-space:meta-chat:growth-step'

type GrowthStep = 'observing' | 'proposed' | 'created'

function readGrowthStep(): GrowthStep {
  try {
    const stored = localStorage.getItem(growthStepStorageKey)
    return stored === 'proposed' || stored === 'created' ? stored : 'observing'
  } catch {
    return 'observing'
  }
}

function writeGrowthStep(step: GrowthStep) {
  try {
    localStorage.setItem(growthStepStorageKey, step)
  } catch {
    // Local storage is only used to keep this prototype state between refreshes.
  }
}

export function MetaChat({
  hermesUiUrl = defaultHermesUiUrl,
  onCreateSpace,
  onPreviewSpace,
}: MetaChatProps) {
  const [growthStep, setGrowthStep] = useState<GrowthStep>(readGrowthStep)

  const updateGrowthStep = (step: GrowthStep) => {
    writeGrowthStep(step)
    setGrowthStep(step)
  }

  const reloadHermes = () => {
    const frame = document.getElementById('hermes-agent-frame') as HTMLIFrameElement | null
    if (frame) frame.src = hermesUiUrl
  }

  return (
    <section className="agent-home">
      <header className="agent-topbar">
        <div className="agent-title">
          <span className="agent-badge">
            <Bot size={18} />
          </span>
          <div>
            <p>AI Space</p>
            <h1>通用 Agent</h1>
          </div>
        </div>
        <div className="agent-toolbar">
          <span className="model-chip">Claude Sonnet 4.6</span>
          <button className="ghost-button" onClick={reloadHermes} type="button">
            <RefreshCcw size={15} />
            刷新
          </button>
          <a className="solid-button" href={hermesUiUrl} rel="noreferrer" target="_blank">
            <ExternalLink size={15} />
            打开
          </a>
        </div>
      </header>

      <div className="agent-canvas">
        <main className="agent-workbench" aria-label="Hermes Agent">
          <div className="workbench-bar">
            <span>
              <MonitorCog size={16} />
              Hermes UI
            </span>
            <code>{hermesUiUrl}</code>
          </div>
          <iframe
            id="hermes-agent-frame"
            className="hermes-frame"
            src={hermesUiUrl}
            title="Hermes Agent Chat"
          />
        </main>

        <GrowthLens
          growthStep={growthStep}
          onAnalyze={() => updateGrowthStep('proposed')}
          onCreate={() => {
            updateGrowthStep('created')
            onCreateSpace?.('ppt')
          }}
          onPreview={() => onPreviewSpace?.('ppt')}
        />
      </div>
    </section>
  )
}

function GrowthLens({
  growthStep,
  onAnalyze,
  onCreate,
  onPreview,
}: {
  growthStep: GrowthStep
  onAnalyze: () => void
  onCreate: () => void
  onPreview: () => void
}) {
  const hasProposal = growthStep !== 'observing'

  return (
    <aside className="growth-lens" aria-label="Space Growth">
      <div className="lens-header">
        <span>
          <GitBranch size={16} />
              空间生长
        </span>
        <small>{growthStep === 'created' ? '已创建' : hasProposal ? '可创建' : '观察中'}</small>
      </div>

      <div className="growth-timeline">
        <GrowthStepRow active done title="1. 对话" text="通用 Agent 是产品主入口。" />
        <GrowthStepRow
          active={hasProposal}
          done={hasProposal}
          title="2. 识别"
          text="发现重复的 PPT 工作流。"
        />
        <GrowthStepRow
          active={hasProposal}
          done={growthStep === 'created'}
          title="3. 提案"
          text="生成一个专属 PPT 工作台。"
        />
        <GrowthStepRow
          active={growthStep === 'created'}
          done={growthStep === 'created'}
          title="4. 长出"
          text="空间进入左侧导航。"
        />
      </div>

      {hasProposal ? (
        <div className="proposal-panel">
          <div className="proposal-kicker">
            <Sparkles size={15} />
            空间提案
          </div>
          <h2>PPT 工作台</h2>
          <p>大纲、画布、品牌样式、演讲稿和进化记录。</p>
          <div className="proposal-actions">
            <button className="ghost-button" onClick={onPreview} type="button">
              <Eye size={15} />
              预览
            </button>
            <button className="solid-button" onClick={onCreate} type="button">
              <PlusCircle size={15} />
              创建
            </button>
          </div>
        </div>
      ) : (
        <button className="solid-button full" onClick={onAnalyze} type="button">
          <Sparkles size={15} />
          分析
        </button>
      )}
    </aside>
  )
}

function GrowthStepRow({
  active,
  done,
  text,
  title,
}: {
  active: boolean
  done: boolean
  text: string
  title: string
}) {
  return (
    <div className={`growth-step-row ${active ? 'active' : ''}`}>
      <span className="step-dot">{done ? <CheckCircle2 size={14} /> : null}</span>
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
    </div>
  )
}
