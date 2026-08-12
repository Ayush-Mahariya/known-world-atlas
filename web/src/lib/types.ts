export type LonLat = [number, number]

export interface Place {
  slug: string
  name: string
  type: 'City' | 'Town' | 'Castle' | 'Ruin' | 'Landmark' | 'Other'
  size: number
  confirmed: boolean
  source: string
  lon: number
  lat: number
  continent: string | null
  continentSource: string | null
  island: string | null
  politicalRegion: string | null
  claimedBy: string | null
  regions: string[]
  terrain: string[]
  nearestRoad: string | null
  milesToRoad: number
}

export interface LoreSource {
  wiki: string
  title: string
  url: string
  canon: 'books' | 'screen'
  license: string
}

export interface Lore {
  slug: string
  name: string
  hasLore: boolean
  summary?: string | null
  description?: string | null
  history?: string | null
  screenHistory?: string | null
  sources: LoreSource[]
}

export interface TerrainMeta {
  width: number
  height: number
  cellDeg: number
  minLon: number
  minLat: number
  milesPerDegree: number
  legend: Record<string, string>
  landCost: Record<string, number>
  seaCost: Record<string, number>
  water: number[]
  counts: Record<string, number>
}

export interface ModeConfig {
  label: string
  milesPerDay: number
  offRoadPenalty?: number
  impassable?: string[]
  flies?: boolean
  sails?: boolean
  note: string
}

export interface TravelConfig {
  modes: Record<string, ModeConfig>
  terrainCost: Record<string, number>
}

export interface RouteResult {
  mode: string
  miles: number
  weightedMiles?: number
  days: number
  path: LonLat[]
  straightLine: boolean
}

export interface RouteFailure {
  mode: string
  error: 'unreachable-endpoint' | 'no-route'
  endpoint?: 'origin' | 'destination'
  message: string
}

export type RouteOutcome = RouteResult | RouteFailure

export function isFailure(r: RouteOutcome): r is RouteFailure {
  return 'error' in r
}
