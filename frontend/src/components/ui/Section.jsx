import React from 'react'

/**
 * Section — the single card shell every dashboard section uses.
 *
 * Before this existed each section hand-rolled its own header, which is why the
 * page had eleven slightly different heading treatments and an emoji per
 * section. One shell means one visual rhythm.
 *
 * Props
 *   id          anchor target, used by the pipeline diagram and the nav
 *   eyebrow     small uppercase kicker; carries real position in the pipeline
 *               ("Stage 02"), never decoration
 *   title       section heading
 *   description one-line explanation, optional
 *   aside       right-hand slot for a headline stat or status chip
 *   tone        'default' | 'lit' (the live demo only) | 'flush' (no padding)
 *   compact     tighter padding for the smaller explainer cards
 */
export default function Section({
  id,
  eyebrow,
  title,
  description,
  aside,
  tone = 'default',
  compact = false,
  className = '',
  children,
}) {
  const shell = tone === 'lit' ? 'card-lit' : 'card'
  const pad = compact ? 'p-5' : 'p-6'

  return (
    <section id={id} className={`scroll-mt-28 ${className}`}>
      <div className={`${shell} ${pad}`}>
        {(title || eyebrow || aside) && (
          <header className="flex items-start justify-between gap-5 mb-5">
            <div className="min-w-0">
              {eyebrow && (
                <p className={`eyebrow mb-1.5 ${tone === 'lit' ? 'eyebrow-accent' : ''}`}>
                  {eyebrow}
                </p>
              )}
              {title && <h2 className="section-title">{title}</h2>}
              {description && <p className="section-sub mt-1.5">{description}</p>}
            </div>
            {aside && <div className="shrink-0">{aside}</div>}
          </header>
        )}
        {children}
      </div>
    </section>
  )
}

/** A labelled figure. Used wherever a section reports a headline number. */
export function Stat({ label, value, unit, accent = false, live = false }) {
  return (
    <div className="panel px-3.5 py-3">
      <p className="label mb-1.5">{label}</p>
      <div className="flex items-baseline gap-1.5">
        <span className={`stat-value ${accent ? 'text-[#818cf8]' : 'text-white'}`}>{value}</span>
        {unit && <span className="text-xs text-[#6b7683]">{unit}</span>}
        {live && (
          <span className="text-[10px] text-[#34d399] uppercase tracking-wider font-medium">
            live
          </span>
        )}
      </div>
    </div>
  )
}

/** Row of stats with a consistent grid. */
export function StatRow({ children, cols = 4 }) {
  const map = { 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-3', 4: 'sm:grid-cols-2 lg:grid-cols-4' }
  return <div className={`grid grid-cols-2 ${map[cols] || map[4]} gap-2.5`}>{children}</div>
}
