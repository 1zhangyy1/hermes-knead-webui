import type { SpaceCatalogItem } from '@ai-space/space-runtime'
import { Bot, LayoutDashboard, WandSparkles } from 'lucide-react'

export function SpacePlaceholder({ space }: { space: SpaceCatalogItem }) {
  return (
    <section className="placeholder-space">
      <div>
        <p className="eyebrow">Space draft</p>
        <h1>{space.name}</h1>
        <p>{space.description}</p>
      </div>
      <div className="placeholder-grid">
        <div className="plain-panel">
          <LayoutDashboard size={22} />
          <span>Scenario surface</span>
        </div>
        <div className="plain-panel">
          <Bot size={22} />
          <span>Dedicated Agent</span>
        </div>
        <div className="plain-panel">
          <WandSparkles size={22} />
          <span>Evolution path</span>
        </div>
      </div>
    </section>
  )
}
