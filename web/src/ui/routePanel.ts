/** Route planner: pick two places, compare every way of getting between them. */
import type { Mode } from '../lib/router'
import type { Place, RouteOutcome } from '../lib/types'
import { isFailure } from '../lib/types'

export const MODE_COLOURS: Record<string, string> = {
  foot: '#6b7f4a',
  horse: '#8a5a2b',
  carriage: '#7a6a90',
  dragon: '#a8323a',
  ship: '#2f6b8a',
}

const MODE_ICONS: Record<string, string> = {
  foot: '🚶', horse: '🐎', carriage: '🛞', dragon: '🐉', ship: '⛵',
}

/** "46.8" days -> "1 month, 2 weeks" — nobody plans a ride in decimal days. */
export function humaniseDays(days: number): string {
  if (days < 1 / 24) return 'less than an hour'
  if (days < 1) {
    const hours = Math.round(days * 24)
    return `${hours} hour${hours === 1 ? '' : 's'}`
  }
  if (days < 14) {
    const d = Math.round(days)
    return `${d} day${d === 1 ? '' : 's'}`
  }
  const totalDays = Math.round(days)
  const months = Math.floor(totalDays / 30)
  const weeks = Math.round((totalDays % 30) / 7)
  if (!months) return `${Math.round(totalDays / 7)} weeks`
  const parts = [`${months} month${months === 1 ? '' : 's'}`]
  if (weeks) parts.push(`${weeks} week${weeks === 1 ? '' : 's'}`)
  return parts.join(', ')
}

export class RoutePanel {
  private el: HTMLElement
  private results: HTMLElement
  private fromEl: HTMLElement
  private toEl: HTMLElement
  private onChange?: () => void
  private onHover?: (mode: string | null) => void
  private onSwap?: () => void
  private onClear?: () => void

  from: Place | null = null
  to: Place | null = null

  constructor(root: HTMLElement) {
    this.el = document.createElement('aside')
    this.el.className = 'panel route-panel'
    this.el.innerHTML = `
      <header>
        <h2>Plan a journey</h2>
        <p class="hint">Click any place on the map, then send it to a slot.</p>
      </header>
      <div class="route-slots">
        <div class="slot" data-slot="from"><span class="slot-label">From</span>
          <span class="slot-value">—</span></div>
        <button class="swap" title="Swap">⇅</button>
        <div class="slot" data-slot="to"><span class="slot-label">To</span>
          <span class="slot-value">—</span></div>
      </div>
      <div class="route-results"></div>
      <button class="clear" hidden>Clear route</button>`
    root.appendChild(this.el)

    this.results = this.el.querySelector('.route-results')!
    this.fromEl = this.el.querySelector('[data-slot="from"] .slot-value')!
    this.toEl = this.el.querySelector('[data-slot="to"] .slot-value')!
    this.el.querySelector('.swap')!.addEventListener('click', () => this.onSwap?.())
    this.el.querySelector('.clear')!.addEventListener('click', () => this.onClear?.())

    this.results.addEventListener('mouseover', (e) => {
      const row = (e.target as HTMLElement).closest('[data-mode]')
      this.onHover?.(row?.getAttribute('data-mode') ?? null)
    })
    this.results.addEventListener('mouseleave', () => this.onHover?.(null))
  }

  on(handlers: {
    change?: () => void
    hover?: (mode: string | null) => void
    swap?: () => void
    clear?: () => void
  }) {
    this.onChange = handlers.change
    this.onHover = handlers.hover
    this.onSwap = handlers.swap
    this.onClear = handlers.clear
  }

  setEndpoints(from: Place | null, to: Place | null) {
    this.from = from
    this.to = to
    this.fromEl.textContent = from?.name ?? '—'
    this.toEl.textContent = to?.name ?? '—'
    this.el.querySelector<HTMLButtonElement>('.clear')!.hidden = !from && !to
    this.onChange?.()
  }

  renderPending() {
    this.results.innerHTML = `<p class="hint">Pick both ends of the journey.</p>`
  }

  render(outcomes: Array<{ mode: Mode; result: RouteOutcome }>) {
    const usable = outcomes.filter((o) => !isFailure(o.result))
    // rank by time, because that is what a traveller actually cares about
    usable.sort((a, b) => (a.result as { days: number }).days - (b.result as { days: number }).days)
    const blocked = outcomes.filter((o) => isFailure(o.result))

    const rows = usable.map(({ mode, result }) => {
      if (isFailure(result)) return ''
      return `
        <li class="result" data-mode="${mode.key}" style="--mode-colour:${MODE_COLOURS[mode.key]}">
          <div class="result-head">
            <span class="mode-icon">${MODE_ICONS[mode.key] ?? '•'}</span>
            <span class="mode-label">${mode.label}</span>
            <span class="mode-time">${humaniseDays(result.days)}</span>
          </div>
          <div class="result-meta">
            ${Math.round(result.miles).toLocaleString()} miles
            &middot; ${mode.milesPerDay} mi/day
            ${result.straightLine ? '&middot; direct flight' : ''}
          </div>
          <p class="mode-note">${mode.note}</p>
        </li>`
    }).join('')

    const blockedRows = blocked.map(({ mode, result }) => {
      if (!isFailure(result)) return ''
      return `<li class="result blocked">
        <span class="mode-icon">${MODE_ICONS[mode.key] ?? '•'}</span>
        <span class="mode-label">${mode.label}</span>
        <span class="blocked-why">${result.message}</span>
      </li>`
    }).join('')

    this.results.innerHTML = `
      ${rows ? `<ul class="results">${rows}</ul>` : ''}
      ${blockedRows ? `<ul class="results blocked-list">${blockedRows}</ul>` : ''}`
  }
}
