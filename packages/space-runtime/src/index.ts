export type SpaceStatus = 'ready' | 'draft'

export type SpaceManifest = {
  id: string
  name: string
  type: string
  description: string
  status: SpaceStatus
  signal: string
  version: string
  entry: string
  agent: {
    defaultInstructions: string
    memoryScope: string
    skills: string[]
  }
  permissions: {
    files: 'none' | 'workspace'
    network: 'none' | 'limited' | 'open'
    shell: 'none' | 'approval-required' | 'open'
  }
}

export type SpaceCatalogItem = Pick<
  SpaceManifest,
  'id' | 'name' | 'description' | 'status' | 'signal' | 'type'
>

export function toCatalogItem(manifest: SpaceManifest): SpaceCatalogItem {
  return {
    id: manifest.id,
    name: manifest.name,
    description: manifest.description,
    status: manifest.status,
    signal: manifest.signal,
    type: manifest.type,
  }
}
