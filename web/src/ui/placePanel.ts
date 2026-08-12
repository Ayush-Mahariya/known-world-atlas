/** The slide-in panel showing a place's geography and its history. */
import type { Lore, Place } from '../lib/types'

const TYPE_LABEL: Record<string, string> = {
  City: 'City', Town: 'Town', Castle: 'Castle', Ruin: 'Ruin',
  Landmark: 'Landmark', Other: 'Place',
}

function paragraphs(text: string, max = 14): string {
  return text
    .split('\n\n')
    .filter((p) => p.trim())
    .slice(0, max)
    .map((p) => `<p>${escapeHtml(p.trim())}</p>`)
    .join('')
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!
  ))
}

export class PlacePanel {
  private el: HTMLElement
  private body: HTMLElement
  private onRouteFrom?: (p: Place) => void
  private onRouteTo?: (p: Place) => void
  private current: Place | null = null

  constructor(root: HTMLElement) {
    this.el = document.createElement('aside')
    this.el.className = 'panel place-panel'
    this.el.hidden = true
    this.el.innerHTML = `
      <button class="panel-close" aria-label="Close">&times;</button>
      <div class="panel-body"></div>`
    root.appendChild(this.el)
    this.body = this.el.querySelector('.panel-body')!
    this.el.querySelector('.panel-close')!.addEventListener('click', () => this.hide())

    this.body.addEventListener('click', (e) => {
      const target = (e.target as HTMLElement).closest('[data-action]')
      if (!target || !this.current) return
      const action = target.getAttribute('data-action')
      if (action === 'from') this.onRouteFrom?.(this.current)
      if (action === 'to') this.onRouteTo?.(this.current)
    })
  }

  onRoute(from: (p: Place) => void, to: (p: Place) => void) {
    this.onRouteFrom = from
    this.onRouteTo = to
  }

  hide() {
    this.el.hidden = true
    this.current = null
  }

  show(place: Place, lore: Lore | undefined) {
    this.current = place
    this.el.hidden = false
    this.el.scrollTop = 0

    const facts: string[] = []
    if (place.politicalRegion) {
      facts.push(place.claimedBy
        ? `${place.politicalRegion} &middot; held by House ${escapeHtml(place.claimedBy)}`
        : escapeHtml(place.politicalRegion))
    }
    if (place.continent) facts.push(escapeHtml(place.continent))
    if (place.island) facts.push(`on ${escapeHtml(place.island)}`)
    if (place.terrain.length) facts.push(escapeHtml(place.terrain.join(', ')))
    if (place.nearestRoad && place.milesToRoad < 20) {
      facts.push(`on the ${escapeHtml(place.nearestRoad)}`)
    } else if (place.nearestRoad) {
      facts.push(`${Math.round(place.milesToRoad)} mi from the ${escapeHtml(place.nearestRoad)}`)
    }

    const caveats: string[] = []
    if (!place.confirmed) {
      caveats.push('Position is speculative — the source map infers it rather than showing it.')
    }
    if (place.source === 'custom') {
      caveats.push('Absent from the source GIS data; positioned by hand relative to its neighbours.')
    }
    if (place.continentSource === 'coast-snap') {
      caveats.push('Sits just outside the traced coastline; assigned to the nearest continent.')
    }

    const sections: string[] = []
    if (lore?.summary) sections.push(`<section>${paragraphs(lore.summary, 3)}</section>`)
    if (lore?.description) {
      sections.push(`<section><h3>The place itself</h3>${paragraphs(lore.description, 6)}</section>`)
    }
    if (lore?.history) {
      sections.push(`<section><h3>History</h3>${paragraphs(lore.history)}</section>`)
    }
    if (lore?.screenHistory && lore.screenHistory !== lore.history) {
      sections.push(`<section class="screen-canon">
        <h3>On screen</h3>${paragraphs(lore.screenHistory, 8)}</section>`)
    }
    if (!sections.length) {
      sections.push(`<section class="empty">
        <p>No article matched this place in any of the three wikis. It appears on
        the map but the chronicles are silent.</p></section>`)
    }

    const sources = (lore?.sources ?? []).map((s) => `
      <li><a href="${s.url}" target="_blank" rel="noopener">${escapeHtml(s.wiki)}</a>
      <span class="canon-tag">${s.canon === 'books' ? 'books' : 'screen'}</span></li>`).join('')

    this.body.innerHTML = `
      <header>
        <p class="eyebrow">${TYPE_LABEL[place.type] ?? place.type}</p>
        <h2>${escapeHtml(place.name)}</h2>
        ${facts.length ? `<p class="facts">${facts.join(' &middot; ')}</p>` : ''}
      </header>
      <div class="route-actions">
        <button data-action="from">Travel from here</button>
        <button data-action="to">Travel to here</button>
      </div>
      ${caveats.length ? `<div class="caveats">${caveats
        .map((c) => `<p>${c}</p>`).join('')}</div>` : ''}
      ${sections.join('')}
      ${sources ? `<footer><h3>Sources</h3><ul class="sources">${sources}</ul>
        <p class="licence">Article text is CC BY-SA from the wikis above.</p></footer>` : ''}
    `
  }
}
