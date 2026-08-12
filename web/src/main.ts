import maplibregl, { type GeoJSONSource } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

import { PARCHMENT_LAYERS, buildStyle, type Realm } from './lib/style'
import { TerrainGrid, buildModes, type Mode } from './lib/router'
import type { Lore, Place, RouteOutcome, TravelConfig } from './lib/types'
import { isFailure } from './lib/types'
import { PlacePanel } from './ui/placePanel'
import { MODE_COLOURS, RoutePanel } from './ui/routePanel'
import './style/app.css'

const DATA = './data'
const TILES = './tiles'

// Which places get a marker at which zoom. The source data ranks places 1-5;
// showing all 241 at once turns Westeros into a wall of dots.
const MIN_ZOOM_BY_SIZE: Record<number, number> = { 5: 0, 4: 3.2, 3: 4, 2: 4.8, 1: 5.6 }

const app = document.getElementById('app')!

async function boot() {
  const [gazetteer, lore, travelCfg, realms, grid] = await Promise.all([
    fetch(`${DATA}/gazetteer.json`).then((r) => r.json() as Promise<Place[]>),
    fetch(`${DATA}/lore.json`).then((r) => r.json() as Promise<Lore[]>),
    fetch(`${DATA}/travel-modes.json`).then((r) => r.json() as Promise<TravelConfig>),
    fetch(`${DATA}/realms.json`).then((r) => r.json() as Promise<Realm[]>),
    TerrainGrid.load(DATA),
  ])

  const loreBySlug = new Map(lore.map((l) => [l.slug, l]))
  const modes = buildModes(travelCfg)
  const modeList = Object.values(modes)

  // exactly the area 08_build_dem_tiles.py rasterised
  const demBounds: [number, number, number, number] = [
    grid.minLon,
    grid.minLat,
    grid.minLon + grid.width * grid.cell,
    grid.minLat + grid.height * grid.cell,
  ]

  const map = new maplibregl.Map({
    container: app,
    style: buildStyle(DATA, TILES, demBounds, realms),
    center: [19, 11],
    zoom: 3.7,
    maxZoom: 9,
    minZoom: 2.2,
    maxPitch: 75,
    attributionControl: false,
  })

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-left')
  map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-left')
  map.addControl(new maplibregl.AttributionControl({
    customAttribution:
      'Geometry: cadaei / theMountainGoat / Tear (CC BY-NC-SA 3.0) · ' +
      'Lore: A Wiki of Ice and Fire, ASOIAF Wiki, Game of Thrones Wiki (CC BY-SA) · ' +
      'World of George R. R. Martin',
  }), 'bottom-right')

  const placePanel = new PlacePanel(app)
  const routePanel = new RoutePanel(app)

  let hoveredMode: string | null = null
  let lastOutcomes: Array<{ mode: Mode; result: RouteOutcome }> = []

  if (import.meta.env.DEV) {
    // handy from the console, and how the headless smoke test inspects state
    ;(window as unknown as { __map: maplibregl.Map }).__map = map
  }

  // The view controls exist before the style finishes loading, and MapLibre
  // throws "Style is not done loading" if you touch layer properties early.
  // Anything that mutates layers goes through here.
  let styleReady = false
  const deferred: Array<() => void> = []
  function whenStyleReady(fn: () => void) {
    if (styleReady) fn()
    else deferred.push(fn)
  }

  map.on('load', () => {
    styleReady = true
    map.setTerrain({ source: 'dem', exaggeration: 12 })
    addMarkers()
    addRealmLabels()
    routePanel.renderPending()
    for (const fn of deferred.splice(0)) fn()
  })

  // ---- basemap + realm overlay -------------------------------------------

  function setBasemap(mode: 'parchment' | 'satellite') {
    whenStyleReady(() => applyBasemap(mode))
  }

  function applyBasemap(mode: 'parchment' | 'satellite') {
    const satellite = mode === 'satellite'
    map.setLayoutProperty('satellite', 'visibility', satellite ? 'visible' : 'none')
    for (const id of PARCHMENT_LAYERS) {
      map.setLayoutProperty(id, 'visibility', satellite ? 'none' : 'visible')
    }
    // rivers and roads stay drawn over both, but need to read against dark
    // imagery rather than pale parchment
    map.setPaintProperty('rivers-line', 'line-color', satellite ? '#7fb4cc' : '#7897a3')
    map.setPaintProperty('rivers-line', 'line-opacity', satellite ? 0.55 : 0.8)
    map.setPaintProperty('roads-line', 'line-color', satellite ? '#e0c98f' : '#a38b62')
    map.setPaintProperty('political-line', 'line-color', satellite ? '#f0e2c0' : '#8c7550')
    document.body.classList.toggle('on-satellite', satellite)
  }

  const realmMarkers: Array<{ marker: maplibregl.Marker; realm: Realm }> = []
  let realmsOn = false

  function addRealmLabels() {
    for (const realm of realms) {
      const el = document.createElement('div')
      el.className = 'realm-label hidden'
      el.style.setProperty('--realm-colour', realm.labelColour)
      el.innerHTML = `
        <span class="realm-name">${realm.name}</span>
        ${realm.claimedBy ? `<span class="realm-house">House ${realm.claimedBy}</span>` : ''}`
      realmMarkers.push({
        marker: new maplibregl.Marker({ element: el, anchor: 'center' })
          .setLngLat([realm.lon, realm.lat])
          .addTo(map),
        realm,
      })
    }
    sizeRealmLabels()
  }

  /**
   * Scale each realm label to fit its realm's width on screen.
   *
   * Fixed-size labels overrun their borders badly — "THE WESTERLANDS" is wider
   * than the Westerlands at low zoom, and collides with the crownlands. Sizing
   * the type to the shape is what an atlas does, and it makes the labels grow
   * naturally as you zoom in. Below a legible minimum the label is dropped.
   *
   * @returns the screen boxes the surviving realm labels occupy, so place
   *   names can be laid out around them.
   */
  function sizeRealmLabels(): Array<[number, number, number, number]> {
    if (!realmsOn) return []

    // pass 1 — size each label to its realm and drop the illegibly small
    const shown: Array<{ el: HTMLElement; area: number }> = []
    for (const { marker, realm } of realmMarkers) {
      const el = marker.getElement()
      const [w, s, e, n] = realm.bbox
      const a = map.project([w, s])
      const b = map.project([e, n])
      const widthPx = Math.abs(b.x - a.x)
      const heightPx = Math.abs(b.y - a.y)

      // ~0.62em average glyph advance at this letter-spacing; leave a margin
      const fit = (widthPx * 0.74) / Math.max(4, realm.name.length * 0.62)
      const size = Math.min(23, fit)
      const tooSmall = size < 8.5 || heightPx < 26
      el.classList.toggle('hidden', tooSmall)
      if (!tooSmall) {
        el.style.setProperty('--realm-size', `${size.toFixed(1)}px`)
        shown.push({ el, area: widthPx * heightPx })
      }
    }

    // pass 2 — realm bounding boxes genuinely overlap (the Reach wraps around
    // the stormlands), so sizing alone cannot stop the labels colliding.
    // Biggest realm wins the space; measure once, after pass 1 has laid out.
    shown.sort((a, b) => b.area - a.area)
    const canvas = map.getCanvas().getBoundingClientRect()
    const taken: Array<[number, number, number, number]> = []
    for (const { el } of shown) {
      const r = el.getBoundingClientRect()
      if (!r.width) continue
      // to canvas space, which is what declutter() works in
      const box: [number, number, number, number] = [
        r.left - canvas.left, r.top - canvas.top,
        r.right - canvas.left, r.bottom - canvas.top,
      ]
      const clash = taken.some(([x1, y1, x2, y2]) =>
        box[0] < x2 && box[2] > x1 && box[1] < y2 && box[3] > y1)
      if (clash) el.classList.add('hidden')
      else taken.push(box)
    }
    return taken
  }

  function setRealmsVisible(on: boolean) {
    realmsOn = on
    whenStyleReady(() => {
      for (const id of ['political-fill', 'political-edge']) {
        map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none')
      }
      // place names need re-laying-out either way: turning realms on steals
      // space from them, turning it off gives space back
      if (on) {
        declutter(sizeRealmLabels())
      } else {
        for (const { marker } of realmMarkers) marker.getElement().classList.add('hidden')
        declutter()
      }
    })
  }

  // ---- place markers ------------------------------------------------------

  const markers: Array<{ marker: maplibregl.Marker; place: Place }> = []

  function addMarkers() {
    for (const place of gazetteer) {
      const el = document.createElement('button')
      el.className = `place-marker place-${place.type.toLowerCase()} size-${place.size}`
      el.type = 'button'
      el.innerHTML = `<span class="dot"></span><span class="label">${place.name}</span>`
      el.addEventListener('click', (e) => {
        e.stopPropagation()
        selectPlace(place)
      })
      const marker = new maplibregl.Marker({ element: el, anchor: 'left' })
        .setLngLat([place.lon, place.lat])
        .addTo(map)
      markers.push({ marker, place })
    }
    declutter(sizeRealmLabels())
    map.on('move', scheduleDeclutter)
    map.on('zoom', scheduleDeclutter)
  }

  let declutterQueued = false
  function scheduleDeclutter() {
    if (declutterQueued) return
    declutterQueued = true
    requestAnimationFrame(() => {
      declutterQueued = false
      // realm labels are laid out first and their boxes reserved, so place
      // names step around them rather than printing through them
      declutter(sizeRealmLabels())
    })
  }

  /**
   * Hide markers whose labels would overlap.
   *
   * HTML markers get no collision avoidance from MapLibre (that only comes with
   * symbol layers, which would drag in a glyph server). Important places win:
   * we walk them in size order and drop anything whose label box intersects one
   * already placed.
   */
  function declutter(reserved: Array<[number, number, number, number]> = []) {
    const z = map.getZoom()
    const canvas = map.getCanvas()
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    const taken: Array<[number, number, number, number]> = [...reserved]

    // biggest first, so a village never suppresses a capital
    const ordered = [...markers].sort((a, b) => b.place.size - a.place.size)

    for (const { marker, place } of ordered) {
      const el = marker.getElement()
      const minZoom = MIN_ZOOM_BY_SIZE[place.size] ?? 6
      if (z < minZoom) {
        el.classList.add('hidden')
        continue
      }
      const p = map.project([place.lon, place.lat])
      if (p.x < -50 || p.y < -20 || p.x > w + 200 || p.y > h + 20) {
        el.classList.add('hidden')
        continue
      }
      // approximate the rendered label box; measuring each element would force
      // a layout per marker per frame
      const fontPx = place.size >= 5 ? 15 : place.size >= 4 ? 13.5 : place.size <= 1 ? 11 : 12
      const width = 14 + place.name.length * fontPx * 0.52
      const box: [number, number, number, number] = [
        p.x - 6, p.y - fontPx * 0.75, p.x + width, p.y + fontPx * 0.75,
      ]
      const clash = taken.some(([x1, y1, x2, y2]) =>
        box[0] < x2 && box[2] > x1 && box[1] < y2 && box[3] > y1)
      el.classList.toggle('hidden', clash)
      if (!clash) taken.push(box)
    }
  }

  function selectPlace(place: Place) {
    placePanel.show(place, loreBySlug.get(place.slug))
    map.flyTo({ center: [place.lon, place.lat], zoom: Math.max(map.getZoom(), 5), speed: 0.7 })
  }

  placePanel.onRoute(
    (p) => routePanel.setEndpoints(p, routePanel.to),
    (p) => routePanel.setEndpoints(routePanel.from, p),
  )

  // ---- routing ------------------------------------------------------------

  routePanel.on({
    change: recomputeRoutes,
    swap: () => routePanel.setEndpoints(routePanel.to, routePanel.from),
    clear: () => routePanel.setEndpoints(null, null),
    hover: (mode) => {
      hoveredMode = mode
      drawRoutes()
    },
  })

  function recomputeRoutes() {
    const { from, to } = routePanel
    if (!from || !to) {
      lastOutcomes = []
      routePanel.renderPending()
      drawRoutes()
      drawEndpoints()
      return
    }
    const started = performance.now()
    lastOutcomes = modeList.map((mode) => ({
      mode,
      result: grid.route(mode, [from.lon, from.lat], [to.lon, to.lat]),
    }))
    console.debug(`routed ${modeList.length} modes in ${(performance.now() - started).toFixed(0)}ms`)
    routePanel.render(lastOutcomes)
    drawRoutes()
    drawEndpoints()
    fitRoutes()
  }

  function drawRoutes() {
    const features = lastOutcomes
      .filter((o) => !isFailure(o.result))
      .filter((o) => !hoveredMode || o.mode.key === hoveredMode)
      .map(({ mode, result }) => {
        const r = result as Extract<RouteOutcome, { path: unknown }>
        return {
          type: 'Feature' as const,
          properties: {
            mode: mode.key,
            colour: MODE_COLOURS[mode.key] ?? '#333',
            straightLine: r.straightLine,
          },
          geometry: { type: 'LineString' as const, coordinates: r.path },
        }
      })
    const src = map.getSource('route') as GeoJSONSource | undefined
    src?.setData({ type: 'FeatureCollection', features })
  }

  function drawEndpoints() {
    const { from, to } = routePanel
    const features = [
      from && { place: from, colour: '#2f6b8a' },
      to && { place: to, colour: '#a8323a' },
    ].filter(Boolean).map((e) => {
      const { place, colour } = e as { place: Place; colour: string }
      return {
        type: 'Feature' as const,
        properties: { colour },
        geometry: { type: 'Point' as const, coordinates: [place.lon, place.lat] },
      }
    })
    const src = map.getSource('endpoints') as GeoJSONSource | undefined
    src?.setData({ type: 'FeatureCollection', features })
  }

  function fitRoutes() {
    const { from, to } = routePanel
    if (!from || !to) return
    const bounds = new maplibregl.LngLatBounds([from.lon, from.lat], [from.lon, from.lat])
    bounds.extend([to.lon, to.lat])
    map.fitBounds(bounds, { padding: { top: 90, bottom: 90, left: 380, right: 380 }, duration: 900 })
  }

  // ---- search -------------------------------------------------------------

  buildSearch(gazetteer, selectPlace)

  // ---- view controls ------------------------------------------------------

  buildViewControls(map, setBasemap, setRealmsVisible, realms)
}

function buildSearch(places: Place[], onPick: (p: Place) => void) {
  const box = document.createElement('div')
  box.className = 'search'
  box.innerHTML = `
    <input type="search" placeholder="Search the Known World…" autocomplete="off"
           aria-label="Search places" />
    <ul class="search-results" hidden></ul>`
  app.appendChild(box)

  const input = box.querySelector('input')!
  const list = box.querySelector('ul')!

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase()
    if (q.length < 2) { list.hidden = true; return }
    const hits = places
      .filter((p) => p.name.toLowerCase().includes(q))
      .sort((a, b) => {
        const aStarts = a.name.toLowerCase().startsWith(q) ? 0 : 1
        const bStarts = b.name.toLowerCase().startsWith(q) ? 0 : 1
        return aStarts - bStarts || b.size - a.size || a.name.localeCompare(b.name)
      })
      .slice(0, 10)
    list.innerHTML = hits.map((p) => `
      <li><button data-slug="${p.slug}">
        <span>${p.name}</span>
        <small>${[p.type, p.politicalRegion ?? p.continent].filter(Boolean).join(' · ')}</small>
      </button></li>`).join('')
    list.hidden = !hits.length
  })

  list.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest('button[data-slug]')
    if (!btn) return
    const place = places.find((p) => p.slug === btn.getAttribute('data-slug'))
    if (place) {
      onPick(place)
      list.hidden = true
      input.value = ''
    }
  })

  document.addEventListener('click', (e) => {
    if (!box.contains(e.target as Node)) list.hidden = true
  })
}

function buildViewControls(
  map: maplibregl.Map,
  setBasemap: (mode: 'parchment' | 'satellite') => void,
  setRealmsVisible: (on: boolean) => void,
  realms: Realm[],
) {
  const box = document.createElement('div')
  box.className = 'view-controls'
  box.innerHTML = `
    <div class="control-group">
      <button data-basemap="parchment" class="active">Map</button>
      <button data-basemap="satellite">Satellite</button>
    </div>
    <div class="control-group">
      <button data-view="flat" class="active">Flat</button>
      <button data-view="tilted">3D</button>
      <button data-view="globe">Globe</button>
    </div>
    <label class="exaggeration">
      Relief
      <input type="range" min="0" max="30" step="1" value="12" />
    </label>
    <label class="toggle">
      <input type="checkbox" data-realms /> Realms
    </label>`
  app.appendChild(box)

  const legend = buildRealmLegend(realms)

  box.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest('button[data-basemap]')
    if (!btn) return
    box.querySelectorAll('button[data-basemap]').forEach((b) => b.classList.remove('active'))
    btn.classList.add('active')
    setBasemap(btn.getAttribute('data-basemap') as 'parchment' | 'satellite')
  })

  box.querySelector<HTMLInputElement>('[data-realms]')!
    .addEventListener('change', (e) => {
      const on = (e.target as HTMLInputElement).checked
      setRealmsVisible(on)
      legend.hidden = !on
    })

  box.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest('button[data-view]')
    if (!btn) return
    box.querySelectorAll('button[data-view]').forEach((b) => b.classList.remove('active'))
    btn.classList.add('active')
    const view = btn.getAttribute('data-view')
    if (view === 'flat') {
      map.setProjection({ type: 'mercator' })
      map.easeTo({ pitch: 0, bearing: 0, duration: 700 })
    } else if (view === 'tilted') {
      map.setProjection({ type: 'mercator' })
      map.easeTo({ pitch: 62, duration: 900 })
    } else {
      map.setProjection({ type: 'globe' })
      map.easeTo({ pitch: 0, duration: 900 })
    }
  })

  box.querySelector<HTMLInputElement>('.exaggeration input')!
    .addEventListener('input', (e) => {
      const v = Number((e.target as HTMLInputElement).value)
      map.setTerrain(v > 0 ? { source: 'dem', exaggeration: v } : null)
    })
}

/** Rainbow key for the realm overlay, ordered north to south like the palette. */
function buildRealmLegend(realms: Realm[]): HTMLElement {
  const el = document.createElement('div')
  el.className = 'realm-legend'
  el.hidden = true
  el.innerHTML = `
    <h3>The realms</h3>
    <ul>${realms.map((r) => `
      <li>
        <span class="swatch" style="background:${r.colour}"></span>
        <span class="realm">${r.name}</span>
        ${r.claimedBy ? `<small>House ${r.claimedBy}</small>` : ''}
      </li>`).join('')}
    </ul>`
  app.appendChild(el)
  return el
}

boot().catch((err) => {
  console.error(err)
  app.innerHTML = `<div class="fatal"><h1>The map is lost</h1>
    <p>${err instanceof Error ? err.message : String(err)}</p>
    <p class="hint">Have you run the pipeline and <code>scripts/sync-web-data.sh</code>?</p></div>`
})
