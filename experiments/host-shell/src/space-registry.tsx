import { MetaChat } from '@ai-space/meta-chat'
import { PptStudio } from '@ai-space/ppt-studio'
import type { SpaceManifest } from '@ai-space/space-runtime'
import { SpacePlaceholder } from './space-placeholder'

export function SpaceHost({
  gatewayOnline,
  manifest,
  onCreateSpace,
  onPreviewSpace,
}: {
  gatewayOnline: boolean
  manifest: SpaceManifest
  onCreateSpace?: (spaceId: string) => void
  onPreviewSpace?: (spaceId: string) => void
}) {
  if (manifest.id === 'meta-chat') {
    return <MetaChat onCreateSpace={onCreateSpace} onPreviewSpace={onPreviewSpace} />
  }

  if (manifest.id === 'ppt') {
    return (
      <PptStudio
        agentInstructions={manifest.agent.defaultInstructions}
        gatewayOnline={gatewayOnline}
      />
    )
  }

  return <SpacePlaceholder space={manifest} />
}
