/**
 * Multi-modal route finding across the Known World.
 *
 * A direct port of pipeline/travel.py — that module is the reference
 * implementation and pipeline/07_validate_routing.py is what pins the numbers
 * to canon. If you change the cost model, change it there first, re-run the
 * validator, then mirror it here.
 *
 * A* runs over the terrain grid (one node per ~8-mile cell, 8-connected) using
 * typed arrays and a binary heap, so a continent-crossing query resolves in a
 * few milliseconds without a worker.
 */
import type {
  LonLat, ModeConfig, RouteOutcome, TerrainMeta, TravelConfig,
} from './types'

// terrain codes, mirroring pipeline/06_build_terrain_grid.py
export const OCEAN = 0, PLAINS = 1, STEPPE = 2, FOREST = 3, DESERT = 4,
  SWAMP = 5, HILLS = 6, MOUNTAIN = 7, LAKE = 8, ROAD = 9

const TERRAIN_BY_NAME: Record<string, number> = {
  ocean: OCEAN, plains: PLAINS, steppe: STEPPE, forest: FOREST, desert: DESERT,
  swamp: SWAMP, hills: HILLS, mountain: MOUNTAIN, lake: LAKE, road: ROAD,
}

const SNAP_RADIUS_LAND = 24 // ~195 miles: islands can be smaller than a cell
const SNAP_RADIUS_SEA = 5   // ~40 miles: a port must actually be near the water

const NEIGHBOURS: ReadonlyArray<readonly [number, number]> = [
  [-1, -1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1],
]

/** Binary min-heap over (priority, cellIndex) pairs held in parallel arrays. */
class MinHeap {
  private prio: Float64Array
  private item: Int32Array
  private size = 0

  constructor(capacity: number) {
    this.prio = new Float64Array(capacity)
    this.item = new Int32Array(capacity)
  }

  private grow() {
    const p = new Float64Array(this.prio.length * 2)
    const i = new Int32Array(this.item.length * 2)
    p.set(this.prio); i.set(this.item)
    this.prio = p; this.item = i
  }

  get length() { return this.size }

  push(priority: number, value: number) {
    if (this.size === this.prio.length) this.grow()
    let n = this.size++
    this.prio[n] = priority
    this.item[n] = value
    while (n > 0) {
      const parent = (n - 1) >> 1
      if (this.prio[parent] <= this.prio[n]) break
      this.swap(parent, n)
      n = parent
    }
  }

  pop(): number {
    const top = this.item[0]
    this.size--
    if (this.size > 0) {
      this.prio[0] = this.prio[this.size]
      this.item[0] = this.item[this.size]
      let n = 0
      for (;;) {
        const l = 2 * n + 1, r = l + 1
        let smallest = n
        if (l < this.size && this.prio[l] < this.prio[smallest]) smallest = l
        if (r < this.size && this.prio[r] < this.prio[smallest]) smallest = r
        if (smallest === n) break
        this.swap(smallest, n)
        n = smallest
      }
    }
    return top
  }

  private swap(a: number, b: number) {
    const p = this.prio[a]; this.prio[a] = this.prio[b]; this.prio[b] = p
    const i = this.item[a]; this.item[a] = this.item[b]; this.item[b] = i
  }
}

export interface Mode {
  key: string
  label: string
  milesPerDay: number
  offRoadPenalty: number
  impassable: Set<number>
  flies: boolean
  sails: boolean
  note: string
}

export function buildModes(cfg: TravelConfig): Record<string, Mode> {
  const out: Record<string, Mode> = {}
  for (const [key, m] of Object.entries(cfg.modes) as [string, ModeConfig][]) {
    out[key] = {
      key,
      label: m.label,
      milesPerDay: m.milesPerDay,
      offRoadPenalty: m.offRoadPenalty ?? 1,
      impassable: new Set((m.impassable ?? []).map((t) => TERRAIN_BY_NAME[t])),
      flies: !!m.flies,
      sails: !!m.sails,
      note: m.note,
    }
  }
  return out
}

export class TerrainGrid {
  readonly width: number
  readonly height: number
  readonly cell: number
  readonly minLon: number
  readonly minLat: number
  readonly milesPerDegree: number
  readonly landCost: Float64Array
  readonly seaCost: Float64Array
  readonly data: Uint8Array
  /** reused across queries so repeated routing doesn't reallocate 550k-cell buffers */
  private gScore: Float64Array
  private cameFrom: Int32Array
  private closed: Uint8Array
  private stamp: Int32Array
  private epoch = 0

  constructor(meta: TerrainMeta, data: Uint8Array) {
    this.width = meta.width
    this.height = meta.height
    this.cell = meta.cellDeg
    this.minLon = meta.minLon
    this.minLat = meta.minLat
    this.milesPerDegree = meta.milesPerDegree
    this.data = data

    this.landCost = new Float64Array(16)
    for (const [k, v] of Object.entries(meta.landCost)) this.landCost[+k] = v
    this.seaCost = new Float64Array(16)
    for (const [k, v] of Object.entries(meta.seaCost)) this.seaCost[+k] = v

    const n = this.width * this.height
    this.gScore = new Float64Array(n)
    this.cameFrom = new Int32Array(n)
    this.closed = new Uint8Array(n)
    this.stamp = new Int32Array(n)
  }

  static async load(dataUrl: string): Promise<TerrainGrid> {
    const [meta, bin] = await Promise.all([
      fetch(`${dataUrl}/terrain.json`).then((r) => r.json() as Promise<TerrainMeta>),
      fetch(`${dataUrl}/terrain.bin`).then((r) => r.arrayBuffer()),
    ])
    return new TerrainGrid(meta, new Uint8Array(bin))
  }

  at(x: number, y: number): number {
    return this.data[y * this.width + x]
  }

  toCell(lon: number, lat: number): [number, number] {
    return [
      Math.min(this.width - 1, Math.max(0, Math.floor((lon - this.minLon) / this.cell))),
      Math.min(this.height - 1, Math.max(0, Math.floor((lat - this.minLat) / this.cell))),
    ]
  }

  toLonLat(x: number, y: number): LonLat {
    return [
      this.minLon + (x + 0.5) * this.cell,
      this.minLat + (y + 0.5) * this.cell,
    ]
  }

  /** Nearest cell whose terrain is allowed, searched in expanding square rings. */
  snap(lon: number, lat: number, allowed: Set<number>, radius: number): [number, number] | null {
    const [cx, cy] = this.toCell(lon, lat)
    if (allowed.has(this.at(cx, cy))) return [cx, cy]
    for (let r = 1; r <= radius; r++) {
      for (let dx = -r; dx <= r; dx++) {
        for (const dy of [-r, r]) {
          const x = cx + dx, y = cy + dy
          if (x >= 0 && x < this.width && y >= 0 && y < this.height && allowed.has(this.at(x, y))) {
            return [x, y]
          }
        }
      }
      for (let dy = -r + 1; dy < r; dy++) {
        for (const dx of [-r, r]) {
          const x = cx + dx, y = cy + dy
          if (x >= 0 && x < this.width && y >= 0 && y < this.height && allowed.has(this.at(x, y))) {
            return [x, y]
          }
        }
      }
    }
    return null
  }

  private passableSet(mode: Mode): Set<number> {
    // Ocean only for ships. Lakes are water but land-locked; snapping a port
    // into an enclosed lagoon strands the route.
    if (mode.sails) return new Set([OCEAN])
    const out = new Set<number>()
    for (let c = 0; c < 16; c++) {
      if (this.landCost[c] > 0 && !mode.impassable.has(c)) out.add(c)
    }
    return out
  }

  route(mode: Mode, start: LonLat, end: LonLat): RouteOutcome {
    const cellMiles = this.cell * this.milesPerDegree

    if (mode.flies) {
      const miles = Math.hypot(end[0] - start[0], end[1] - start[1]) * this.milesPerDegree
      return {
        mode: mode.key,
        miles,
        days: miles / mode.milesPerDay,
        path: [start, end],
        straightLine: true,
      }
    }

    const allowed = this.passableSet(mode)
    const costs = mode.sails ? this.seaCost : this.landCost
    const radius = mode.sails ? SNAP_RADIUS_SEA : SNAP_RADIUS_LAND

    const s = this.snap(start[0], start[1], allowed, radius)
    const e = this.snap(end[0], end[1], allowed, radius)
    if (!s || !e) {
      const endpoint = !s ? 'origin' : 'destination'
      const reason = mode.sails ? 'no navigable water' : 'no passable ground'
      return {
        mode: mode.key,
        error: 'unreachable-endpoint',
        endpoint,
        message: `${reason} near the ${endpoint} for travel ${mode.label.toLowerCase()}`,
      }
    }

    let minCost = Infinity
    for (const c of allowed) if (costs[c] < minCost) minCost = costs[c]

    const { width } = this
    const startIdx = s[1] * width + s[0]
    const goalIdx = e[1] * width + e[0]
    const [ex, ey] = e

    const epoch = ++this.epoch
    const { gScore, cameFrom, closed, stamp } = this
    const heap = new MinHeap(1 << 14)

    const heuristic = (x: number, y: number) => {
      const dx = Math.abs(x - ex), dy = Math.abs(y - ey)
      const steps = dx + dy + (Math.SQRT2 - 2) * Math.min(dx, dy)
      return steps * cellMiles * minCost
    }

    stamp[startIdx] = epoch
    gScore[startIdx] = 0
    cameFrom[startIdx] = -1
    closed[startIdx] = 0
    heap.push(heuristic(s[0], s[1]), startIdx)

    let found = false
    while (heap.length) {
      const current = heap.pop()
      if (stamp[current] === epoch && closed[current]) continue
      closed[current] = 1
      if (current === goalIdx) { found = true; break }

      const cx = current % width, cy = (current / width) | 0
      const gCur = gScore[current]
      for (const [dx, dy] of NEIGHBOURS) {
        const nx = cx + dx, ny = cy + dy
        if (nx < 0 || nx >= width || ny < 0 || ny >= this.height) continue
        const terrain = this.at(nx, ny)
        if (!allowed.has(terrain)) continue
        const nIdx = ny * width + nx
        if (stamp[nIdx] === epoch && closed[nIdx]) continue

        const step = cellMiles * (dx && dy ? Math.SQRT2 : 1)
        let weight = costs[terrain]
        if (!mode.sails && terrain !== ROAD) weight *= mode.offRoadPenalty
        const tentative = gCur + step * weight

        if (stamp[nIdx] !== epoch) {
          stamp[nIdx] = epoch
          gScore[nIdx] = Infinity
          closed[nIdx] = 0
        }
        if (tentative < gScore[nIdx]) {
          gScore[nIdx] = tentative
          cameFrom[nIdx] = current
          heap.push(tentative + heuristic(nx, ny), nIdx)
        }
      }
    }

    if (!found) {
      return {
        mode: mode.key,
        error: 'no-route',
        message: `no continuous ${mode.label.toLowerCase()} route exists between these places`,
      }
    }

    let cells: number[] = []
    for (let c = goalIdx; c !== -1; c = cameFrom[c]) cells.push(c)
    cells.reverse()

    const offRoad = mode.sails ? 1 : mode.offRoadPenalty
    cells = this.smooth(cells, allowed, costs, offRoad, cellMiles)

    let miles = 0, weighted = 0
    const path: LonLat[] = []
    for (let i = 0; i < cells.length; i++) {
      const idx = cells[i]
      const x = idx % width, y = (idx / width) | 0
      path.push(this.toLonLat(x, y))
      if (i > 0) {
        const prev = cells[i - 1]
        const px = prev % width, py = (prev / width) | 0
        const step = cellMiles * (px !== x && py !== y ? Math.SQRT2 : 1)
        const terrain = this.at(x, y)
        const w = costs[terrain] * (!mode.sails && terrain !== ROAD ? offRoad : 1)
        miles += step
        weighted += step * w
      }
    }

    return {
      mode: mode.key,
      miles,
      weightedMiles: weighted,
      days: weighted / mode.milesPerDay,
      path,
      straightLine: false,
    }
  }

  /**
   * String-pull the path straight where the terrain allows.
   *
   * An 8-connected grid can only step at 45-degree increments, so a route on any
   * other bearing comes out as a staircase and reads several percent long. Runs
   * of cells are replaced by a straight line whenever that line is passable and
   * costs no more than the steps it replaces.
   */
  private smooth(
    cells: number[], allowed: Set<number>, costs: Float64Array,
    offRoad: number, cellMiles: number,
  ): number[] {
    if (cells.length < 3) return cells
    const { width } = this

    const lineCells = (a: number, b: number): number[] | null => {
      const ax = a % width, ay = (a / width) | 0
      const bx = b % width, by = (b / width) | 0
      const steps = Math.max(Math.abs(bx - ax), Math.abs(by - ay))
      if (steps === 0) return [a]
      const out: number[] = []
      for (let s = 0; s <= steps; s++) {
        const t = s / steps
        const x = Math.round(ax + (bx - ax) * t)
        const y = Math.round(ay + (by - ay) * t)
        if (!allowed.has(this.at(x, y))) return null
        out.push(y * width + x)
      }
      return out
    }

    const runCost = (seq: number[]): number => {
      let total = 0
      for (let i = 1; i < seq.length; i++) {
        const px = seq[i - 1] % width, py = (seq[i - 1] / width) | 0
        const x = seq[i] % width, y = (seq[i] / width) | 0
        const step = cellMiles * (px !== x && py !== y ? Math.SQRT2 : 1)
        const terrain = this.at(x, y)
        total += step * costs[terrain] * (terrain !== ROAD ? offRoad : 1)
      }
      return total
    }

    const out: number[] = [cells[0]]
    let i = 0
    while (i < cells.length - 1) {
      let best = i + 1
      let bestLine: number[] = [cells[i], cells[i + 1]]
      // bounded look-ahead: the check is quadratic in the window, and long
      // straight shots across a continent are rarely valid anyway
      for (let j = Math.min(cells.length - 1, i + 60); j > i + 1; j--) {
        const line = lineCells(cells[i], cells[j])
        if (line && runCost(line) <= runCost(cells.slice(i, j + 1)) + 1e-9) {
          best = j
          bestLine = line
          break
        }
      }
      for (let k = 1; k < bestLine.length; k++) out.push(bestLine[k])
      i = best
    }
    return out
  }
}
