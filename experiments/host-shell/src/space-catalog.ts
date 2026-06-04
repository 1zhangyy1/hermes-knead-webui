import { toCatalogItem, type SpaceCatalogItem, type SpaceManifest } from '@ai-space/space-runtime'
import metaChatManifest from '../../../spaces/meta-chat/space.json'
import pptStudioManifest from '../../../spaces/ppt-studio/space.json'

export const spaceManifests = [
  metaChatManifest as SpaceManifest,
  pptStudioManifest as SpaceManifest,
  {
    id: 'research',
    name: '研究工作台',
    type: 'knowledge.research',
    description: 'Sources, notes, citations, cards, and draft synthesis.',
    status: 'draft',
    signal: '原型',
    version: '0.0.0',
    entry: 'draft',
    agent: {
      defaultInstructions: 'Help the user gather, evaluate, and synthesize research.',
      memoryScope: 'space:research-lab',
      skills: ['source-review', 'citation-management'],
    },
    permissions: {
      files: 'workspace',
      network: 'limited',
      shell: 'approval-required',
    },
  },
  {
    id: 'companion',
    name: '陪伴世界',
    type: 'relationship.companion',
    description: 'A playful, persistent space for memory-rich companionship.',
    status: 'draft',
    signal: '原型',
    version: '0.0.0',
    entry: 'draft',
    agent: {
      defaultInstructions: 'Create a warm, persistent, playful companionship space.',
      memoryScope: 'space:companion-world',
      skills: ['long-term-memory', 'interactive-story'],
    },
    permissions: {
      files: 'none',
      network: 'none',
      shell: 'none',
    },
  },
] satisfies SpaceManifest[]

export const spaces: SpaceCatalogItem[] = spaceManifests.map(toCatalogItem)

export function getSpaceManifest(spaceId: string): SpaceManifest | undefined {
  return spaceManifests.find((manifest) => manifest.id === spaceId)
}
