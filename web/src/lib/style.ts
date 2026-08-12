/**
 * The parchment style for the Known World.
 *
 * Everything is drawn from our own GeoJSON plus the synthesised DEM — there is
 * no external basemap, tile server or font server involved, so the atlas runs
 * fully offline. Place labels are HTML markers rather than symbol layers,
 * which is what lets us skip a glyph endpoint entirely.
 */
import type {
  DataDrivenPropertyValueSpecification, StyleSpecification,
} from 'maplibre-gl'

export const PALETTE = {
  ocean: '#9db6bd',
  oceanDeep: '#87a4ad',
  land: '#e9dcbf',
  coast: '#b9a67e',
  forest: '#c2cfa2',
  mountain: '#d3c6a6',
  desert: '#ecdcaa',
  steppe: '#ddd6a4',
  swamp: '#b6c29c',
  lake: '#9db6bd',
  river: '#7897a3',
  road: '#a38b62',
  wall: '#f4f8fa',
  border: '#8c7550',
  ink: '#3d3428',
} as const

/**
 * Heraldic colours, kept for reference and for a future "banners" palette.
 * The realm overlay uses the rainbow palette from realms.json instead, because
 * eleven heraldic colours include three greys and two reds and are hard to tell
 * apart as adjacent fills.
 */
export const HOUSE_COLOURS: Record<string, string> = {
  Stark: '#8d9aa5',
  Lannister: '#b23b3b',
  Baratheon: '#c8a33a',
  Tully: '#3f6ea8',
  Arryn: '#5f8fc4',
  Greyjoy: '#4a5b63',
  Tyrell: '#5f9e58',
  Martell: '#d4813a',
  Targaryen: '#8c2f39',
  "Night's Watch": '#4a4a52',
  Wildlings: '#7a6a55',
}

export interface Realm {
  name: string
  sourceName: string
  /** [west, south, east, north] of the realm polygon, for label sizing */
  bbox: [number, number, number, number]
  claimedBy: string | null
  lon: number
  lat: number
  slug: string
  hue: number
  colour: string
  labelColour: string
}

/** Layers that make up the drawn parchment world — hidden under satellite. */
export const PARCHMENT_LAYERS = [
  'land-fill', 'islands-fill', 'regions-fill', 'landscape-fill',
  'hillshade', 'lakes-fill', 'coast-line', 'islands-line',
] as const

/** Layers drawn on top of whichever basemap is active. */
export const SATELLITE_LAYERS = ['satellite'] as const

const LAYER_SOURCES = [
  'land', 'continents', 'islands', 'regions', 'landscape', 'lakes',
  'rivers', 'roads', 'wall', 'political',
] as const

export type LayerSource = typeof LAYER_SOURCES[number]

/**
 * `match` on the realm's source name, spreading in one colour per realm.
 *
 * The style spec types a match expression as a fixed-arity tuple, which a
 * spread cannot satisfy, so the cast is unavoidable — MapLibre still validates
 * the shape at style-load time.
 */
function realmFill(realms: Realm[]): DataDrivenPropertyValueSpecification<string> {
  // A single undefined label makes the whole expression invalid and MapLibre
  // then drops the entire style — the map goes blank with no error. Filter
  // defensively so stale data costs one layer, not the map.
  const pairs = realms
    .filter((r) => typeof r.sourceName === 'string' && typeof r.colour === 'string')
    .flatMap((r) => [r.sourceName, r.colour])

  if (!pairs.length) return '#9d8e70'
  return [
    'match', ['coalesce', ['get', 'name'], ''],
    ...pairs,
    '#9d8e70',
  ] as unknown as DataDrivenPropertyValueSpecification<string>
}

/**
 * @param demBounds [west, south, east, north] covered by the generated DEM.
 *   Without this MapLibre requests tiles outside our coverage; a dev server
 *   answers those with its SPA fallback, and the decoder chokes on HTML served
 *   as a PNG ("The source image could not be decoded").
 */
export function buildStyle(
  dataUrl: string,
  tilesUrl: string,
  demBounds: [number, number, number, number],
  realms: Realm[],
): StyleSpecification {
  const dem = {
    type: 'raster-dem' as const,
    tiles: [`${tilesUrl}/dem/{z}/{x}/{y}.png`],
    encoding: 'mapbox' as const,
    tileSize: 256,
    minzoom: 2,
    maxzoom: 5,
    bounds: demBounds,
  }
  const sources: StyleSpecification['sources'] = {
    // MapLibre warns when one source feeds both 3D terrain and a hillshade
    // layer, so they get their own copies of the same tiles
    dem,
    'dem-shade': { ...dem },
    // Synthesised orbital imagery — see pipeline/09_build_satellite_tiles.py.
    // Same coverage as the DEM, so the same bounds apply.
    satellite: {
      type: 'raster',
      tiles: [`${tilesUrl}/satellite/{z}/{x}/{y}.png`],
      tileSize: 256,
      minzoom: 2,
      maxzoom: 5,
      bounds: demBounds,
    },
  }
  for (const name of LAYER_SOURCES) {
    sources[name] = { type: 'geojson', data: `${dataUrl}/layers/${name}.geojson` }
  }
  sources.route = {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  }
  sources.endpoints = {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  }

  return {
    version: 8,
    name: 'Known World — parchment',
    // no glyphs/sprite: labels are HTML markers, so the style needs neither
    sources,
    sky: {
      'sky-color': '#b7cdd6',
      'sky-horizon-blend': 0.6,
      'horizon-color': '#e2dcc6',
      'horizon-fog-blend': 0.7,
      'fog-color': '#dcd4bb',
      'fog-ground-blend': 0.2,
    },
    light: { anchor: 'map', position: [1.2, 200, 40], intensity: 0.3 },
    layers: [
      { id: 'ocean', type: 'background', paint: { 'background-color': PALETTE.ocean } },

      // the satellite basemap sits directly on the background; the parchment
      // layers below cover it when it is hidden
      {
        id: 'satellite', type: 'raster', source: 'satellite',
        layout: { visibility: 'none' },
        paint: { 'raster-opacity': 1, 'raster-fade-duration': 220 },
      },

      {
        id: 'land-fill', type: 'fill', source: 'land',
        paint: { 'fill-color': PALETTE.land },
      },
      {
        id: 'islands-fill', type: 'fill', source: 'islands',
        paint: { 'fill-color': PALETTE.land },
      },

      // broad biome washes, then the named landscape features on top
      {
        id: 'regions-fill', type: 'fill', source: 'regions',
        filter: ['in', ['get', 'type'], ['literal', ['desert', 'forest', 'mountain']]],
        paint: {
          'fill-color': [
            'match', ['get', 'type'],
            'desert', PALETTE.desert,
            'forest', PALETTE.forest,
            'mountain', PALETTE.mountain,
            PALETTE.land,
          ],
          'fill-opacity': 0.55,
        },
      },
      {
        id: 'landscape-fill', type: 'fill', source: 'landscape',
        paint: {
          'fill-color': [
            'match', ['get', 'type'],
            'forest', PALETTE.forest,
            'mountain', PALETTE.mountain,
            'swamp', PALETTE.swamp,
            'stepp', PALETTE.steppe,
            PALETTE.land,
          ],
          'fill-opacity': 0.75,
        },
      },

      {
        id: 'hillshade', type: 'hillshade', source: 'dem-shade',
        paint: {
          'hillshade-exaggeration': 0.45,
          'hillshade-shadow-color': '#8a7b5c',
          'hillshade-highlight-color': '#fbf3dd',
          'hillshade-accent-color': '#a2926d',
        },
      },

      {
        id: 'lakes-fill', type: 'fill', source: 'lakes',
        paint: { 'fill-color': PALETTE.lake, 'fill-outline-color': PALETTE.river },
      },
      {
        id: 'rivers-line', type: 'line', source: 'rivers',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': PALETTE.river,
          'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.4, 6, 1.4, 9, 3],
          'line-opacity': 0.8,
        },
      },

      {
        id: 'coast-line', type: 'line', source: 'continents',
        paint: {
          'line-color': PALETTE.coast,
          'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 7, 1.8],
        },
      },
      {
        id: 'islands-line', type: 'line', source: 'islands',
        paint: { 'line-color': PALETTE.coast, 'line-width': 0.6 },
      },

      {
        id: 'political-fill', type: 'fill', source: 'political',
        layout: { visibility: 'none' },
        paint: { 'fill-color': realmFill(realms), 'fill-opacity': 0.34 },
      },
      {
        id: 'political-edge', type: 'line', source: 'political',
        layout: { visibility: 'none' },
        paint: { 'line-color': realmFill(realms), 'line-width': 2.2, 'line-opacity': 0.85 },
      },
      {
        id: 'political-line', type: 'line', source: 'political',
        paint: {
          'line-color': PALETTE.border,
          'line-width': 1,
          'line-dasharray': [3, 2],
          'line-opacity': 0.55,
        },
      },

      {
        id: 'roads-line', type: 'line', source: 'roads',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': PALETTE.road,
          'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.8, 6, 2, 9, 3.5],
          'line-dasharray': [4, 2],
        },
      },
      {
        id: 'wall-line', type: 'line', source: 'wall',
        layout: { 'line-cap': 'butt' },
        paint: {
          'line-color': PALETTE.wall,
          'line-width': ['interpolate', ['linear'], ['zoom'], 3, 2, 7, 7],
          'line-opacity': 0.95,
        },
      },

      // route rendering: a soft casing under a solid line, so it reads over any biome
      {
        id: 'route-casing', type: 'line', source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#2b2418', 'line-width': 7, 'line-opacity': 0.25, 'line-blur': 2 },
      },
      // line-dasharray takes no data expressions, so ground and air routes are
      // two layers filtered on the same source rather than one styled by property
      {
        id: 'route-line', type: 'line', source: 'route',
        filter: ['!', ['get', 'straightLine']],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': ['get', 'colour'], 'line-width': 3.2 },
      },
      {
        id: 'route-line-air', type: 'line', source: 'route',
        filter: ['get', 'straightLine'],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'colour'],
          'line-width': 3,
          'line-dasharray': [2, 1.6],
        },
      },
      {
        id: 'endpoint-halo', type: 'circle', source: 'endpoints',
        paint: {
          'circle-radius': 9,
          'circle-color': '#fff8e6',
          'circle-opacity': 0.9,
          'circle-stroke-width': 2.5,
          'circle-stroke-color': ['get', 'colour'],
        },
      },
    ],
  }
}
