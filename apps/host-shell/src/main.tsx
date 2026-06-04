import { StrictMode, useCallback, useEffect, useState, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { createHermesClient } from '@ai-space/hermes-client'
import {
  ArrowUp,
  CheckCircle2,
  Clock3,
  FileText,
  Folder,
  Loader2,
  Mail,
  MessageSquarePlus,
  Paperclip,
  Pin,
  Plug,
  Presentation,
  RefreshCcw,
  Search,
  Settings,
  ShieldAlert,
  Sparkles,
  StopCircle,
  Workflow,
} from 'lucide-react'
import { getSpaceManifest, spaces } from './space-catalog'
import { SpaceHost } from './space-registry'
import './styles.css'

declare global {
  interface Window {
    __aiSpaceRoot?: Root
  }
}

type HealthState = 'checking' | 'online' | 'offline'
type ActiveView = 'home' | 'search' | 'plugins' | 'automations' | string

const hermes = createHermesClient()
const grownSpacesStorageKey = 'ai-space:grown-space-ids'

function readGrownSpaceIds() {
  try {
    const stored = localStorage.getItem(grownSpacesStorageKey)
    if (!stored) return [] as string[]
    const parsed = JSON.parse(stored) as unknown
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string') : []
  } catch {
    return []
  }
}

function App() {
  const [activeView, setActiveView] = useState<ActiveView>('home')
  const [grownSpaceIds, setGrownSpaceIds] = useState<string[]>(readGrownSpaceIds)
  const [health, setHealth] = useState<HealthState>('checking')
  const [dashboardHealth, setDashboardHealth] = useState<HealthState>('checking')

  const refreshHealth = useCallback(async () => {
    setHealth('checking')
    setDashboardHealth('checking')

    hermes.gateway.health().then(() => setHealth('online')).catch(() => setHealth('offline'))
    hermes.dashboard
      .status()
      .then(() => setDashboardHealth('online'))
      .catch(() => setDashboardHealth('offline'))
  }, [])

  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  const createGrownSpace = useCallback((spaceId: string) => {
    setGrownSpaceIds((current) => {
      const next = current.includes(spaceId) ? current : [...current, spaceId]
      localStorage.setItem(grownSpacesStorageKey, JSON.stringify(next))
      return next
    })
    setActiveView(spaceId)
  }, [])

  const grownSpaces = spaces.filter((space) => space.id !== 'meta-chat' && grownSpaceIds.includes(space.id))
  const prototypeSpaces = spaces.filter(
    (space) => space.id !== 'meta-chat' && !grownSpaceIds.includes(space.id),
  )
  const selectedManifest = typeof activeView === 'string' ? getSpaceManifest(activeView) : undefined

  return (
    <div className="app-shell codex-shell">
      <aside className="codex-sidebar" aria-label="Next AI Navigation">
        <nav className="codex-primary-nav">
          <SidebarCommand
            active={activeView === 'home'}
            icon={<MessageSquarePlus size={17} />}
            label="新对话"
            onClick={() => setActiveView('home')}
          />
          <SidebarCommand
            active={activeView === 'search'}
            icon={<Search size={17} />}
            label="搜索"
            onClick={() => setActiveView('search')}
          />
          <SidebarCommand
            active={activeView === 'plugins'}
            icon={<Plug size={17} />}
            label="插件"
            onClick={() => setActiveView('plugins')}
          />
          <SidebarCommand
            active={activeView === 'automations'}
            badge="2"
            icon={<Clock3 size={17} />}
            label="自动化"
            onClick={() => setActiveView('automations')}
          />
        </nav>

        <div className="sidebar-scroll">
          <SidebarSection label="置顶">
            <HistoryItem icon={<Pin size={15} />} label="讨论清楚类型定义" shortcut="⌘1" />
          </SidebarSection>

          <SidebarSection label="项目">
            <ProjectBlock
              name="nextaichat"
              active={activeView === 'home' || selectedManifest?.id === 'meta-chat'}
              onClick={() => setActiveView('home')}
            >
              <HistoryItem label="探讨 AI 产品自进化" shortcut="⌘2" />
              <HistoryItem label="重构 Agent 母体原型" shortcut="⌘3" />
              <NestedSpace
                active={activeView === 'meta-chat'}
                label="通用 Agent"
                onClick={() => setActiveView('meta-chat')}
                state="Hermes UI"
              />
              {grownSpaces.map((space) => (
                <NestedSpace
                  active={activeView === space.id}
                  key={space.id}
                  label={space.name}
                  onClick={() => setActiveView(space.id)}
                  state="已长出"
                />
              ))}
              {prototypeSpaces.map((space) => (
                <NestedSpace
                  active={activeView === space.id}
                  key={space.id}
                  label={space.name}
                  onClick={() => setActiveView(space.id)}
                  state="原型"
                />
              ))}
            </ProjectBlock>

            <ProjectBlock name="maxgent">
              <HistoryItem label="研究聊天后的 AI 自动追问" shortcut="⌘4" />
              <HistoryItem label="评测初始化的体验" shortcut="⌘5" />
            </ProjectBlock>

            <ProjectBlock name="use-cases">
              <HistoryItem label="投放" shortcut="3 天" />
            </ProjectBlock>
          </SidebarSection>
        </div>

        <div className="codex-sidebar-footer">
          <div className="runtime-compact">
            <span>Hermes</span>
            <StatusPill state={health} />
          </div>
          <div className="runtime-compact">
            <span>Dashboard</span>
            <StatusPill state={dashboardHealth} />
          </div>
          <button className="sidebar-command" onClick={refreshHealth} type="button">
            <RefreshCcw size={16} />
            <span>刷新连接</span>
          </button>
          <button className="sidebar-command" type="button">
            <Settings size={16} />
            <span>设置</span>
          </button>
        </div>
      </aside>

      <main className="main-surface codex-main">
        {selectedManifest ? (
          <SpaceHost
            gatewayOnline={health === 'online'}
            manifest={selectedManifest}
            onCreateSpace={createGrownSpace}
            onPreviewSpace={setActiveView}
          />
        ) : activeView === 'home' ? (
          <CodexHome onCreateSpace={createGrownSpace} onOpenAgent={() => setActiveView('meta-chat')} />
        ) : (
          <UtilityView activeView={activeView} />
        )}
      </main>
    </div>
  )
}

function CodexHome({
  onCreateSpace,
  onOpenAgent,
}: {
  onCreateSpace: (spaceId: string) => void
  onOpenAgent: () => void
}) {
  return (
    <section className="codex-home">
      <div className="top-right-controls">
        <span className="tiny-model">5.5</span>
        <button className="icon-only" type="button">
          <Settings size={16} />
        </button>
      </div>

      <div className="codex-home-center">
        <h1>我们该在 nextaichat 中做什么？</h1>

        <div className="codex-composer">
          <textarea placeholder="问问 Next AI。输入 @ 使用插件或提及文件" />
          <div className="composer-toolbar">
            <div className="composer-left">
              <button className="icon-only" type="button">
                <Paperclip size={18} />
              </button>
              <button className="permission-chip" type="button">
                <ShieldAlert size={15} />
                完全访问权限
              </button>
            </div>
            <div className="composer-right">
              <button className="model-button" type="button">
                <Sparkles size={15} />
                5.5
              </button>
              <button className="send-button" onClick={onOpenAgent} type="button">
                <ArrowUp size={18} />
              </button>
            </div>
          </div>
          <div className="composer-project">
            <Folder size={15} />
            nextaichat
          </div>
        </div>

        <div className="connector-grid">
          <ConnectorCard icon={<Plug size={20} />} title="连接消息传送" text="从近期团队讨论中获取背景信息" />
          <ConnectorCard icon={<Mail size={20} />} title="连接电子邮件" text="总结邮件中利益相关方的请求" />
          <ConnectorCard icon={<FileText size={20} />} title="连接文件" text="审查结果、研究资料和计划" />
        </div>

        <div className="growth-strip">
          <div>
            <strong>Space 不是第一层，而是 Agent 在项目里长出的结果。</strong>
            <p>当 nextaichat 里的会话反复出现 PPT 流程，就生成 PPT 工作台；如果反复出现陪伴玩法，就生成陪伴世界。</p>
          </div>
          <button className="solid-button" onClick={() => onCreateSpace('ppt')} type="button">
            <Presentation size={16} />
            长出 PPT 工作台
          </button>
        </div>
      </div>
    </section>
  )
}

function UtilityView({ activeView }: { activeView: ActiveView }) {
  const title =
    activeView === 'search' ? '搜索' : activeView === 'plugins' ? '插件' : activeView === 'automations' ? '自动化' : '工具'
  const copy =
    activeView === 'search'
      ? '搜索会话、项目、文件、空间和 Agent 运行记录。'
      : activeView === 'plugins'
        ? '插件是 Agent 的外部能力，Space 是 Agent 生成的内部应用。'
        : '自动化让 Agent 在未来继续工作，Space 可以订阅这些任务结果。'

  return (
    <section className="utility-view">
      <Workflow size={24} />
      <h1>{title}</h1>
      <p>{copy}</p>
    </section>
  )
}

function SidebarCommand({
  active,
  badge,
  icon,
  label,
  onClick,
}: {
  active?: boolean
  badge?: string
  icon: ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button className={`sidebar-command ${active ? 'active' : ''}`} onClick={onClick} type="button">
      {icon}
      <span>{label}</span>
      {badge ? <small>{badge}</small> : null}
    </button>
  )
}

function SidebarSection({ children, label }: { children: ReactNode; label: string }) {
  return (
    <section className="sidebar-section">
      <div className="sidebar-section-label">{label}</div>
      {children}
    </section>
  )
}

function ProjectBlock({
  active,
  children,
  name,
  onClick,
}: {
  active?: boolean
  children?: ReactNode
  name: string
  onClick?: () => void
}) {
  return (
    <div className="project-block">
      <button className={`project-title ${active ? 'active' : ''}`} onClick={onClick} type="button">
        <Folder size={16} />
        <span>{name}</span>
      </button>
      <div className="project-children">{children}</div>
    </div>
  )
}

function HistoryItem({
  icon,
  label,
  shortcut,
}: {
  icon?: ReactNode
  label: string
  shortcut?: string
}) {
  return (
    <button className="history-item" type="button">
      {icon ? <span>{icon}</span> : null}
      <strong>{label}</strong>
      {shortcut ? <small>{shortcut}</small> : null}
    </button>
  )
}

function NestedSpace({
  active,
  label,
  onClick,
  state,
}: {
  active: boolean
  label: string
  onClick: () => void
  state: string
}) {
  return (
    <button className={`nested-space ${active ? 'active' : ''}`} onClick={onClick} type="button">
      <Presentation size={15} />
      <strong>{label}</strong>
      <small>{state}</small>
    </button>
  )
}

function ConnectorCard({ icon, text, title }: { icon: ReactNode; text: string; title: string }) {
  return (
    <button className="connector-card" type="button">
      <span>{icon}</span>
      <strong>{title}</strong>
      <p>{text}</p>
    </button>
  )
}

function StatusPill({ state }: { state: HealthState }) {
  return (
    <span className={`status-pill ${state}`}>
      {state === 'checking' ? (
        <Loader2 size={13} className="spin" />
      ) : state === 'online' ? (
        <CheckCircle2 size={13} />
      ) : (
        <StopCircle size={13} />
      )}
      {state}
    </span>
  )
}

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('Missing root element')

window.__aiSpaceRoot ??= createRoot(rootElement)
window.__aiSpaceRoot.render(
  <StrictMode>
    <App />
  </StrictMode>,
)
