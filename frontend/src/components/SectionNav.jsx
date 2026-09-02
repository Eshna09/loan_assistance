import React, { useEffect, useState } from 'react'

// The page runs to eleven sections. Without this the only way to reach the
// architecture diagrams is a long scroll.
const LINKS = [
  { id: 'rag-demo', label: 'Ask' },
  { id: 'knowledge-base', label: 'Knowledge base' },
  { id: 'service-architecture', label: 'Services' },
  { id: 'pipeline-overview', label: 'Pipeline' },
  { id: 'chunking', label: 'Chunking' },
  { id: 'embeddings', label: 'Embeddings' },
  { id: 'vector-database', label: 'Vector store' },
  { id: 'api-architecture', label: 'API' },
  { id: 'docker-architecture', label: 'Docker' },
]

export default function SectionNav() {
  const [active, setActive] = useState(LINKS[0].id)

  useEffect(() => {
    const targets = LINKS.map((l) => document.getElementById(l.id)).filter(Boolean)
    if (!targets.length) return

    // Trigger band sits just below the sticky chrome, so the highlighted link
    // matches the section actually under the reader's eye.
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActive(visible[0].target.id)
      },
      { rootMargin: '-120px 0px -65% 0px', threshold: 0 }
    )

    targets.forEach((t) => observer.observe(t))
    return () => observer.disconnect()
  }, [])

  return (
    <nav
      aria-label="Dashboard sections"
      className="sticky top-16 z-40 border-b border-white/10 bg-[#0a0a0f]/90 backdrop-blur-md"
    >
      <div className="max-w-[1240px] mx-auto px-5 sm:px-8">
        <ul className="flex items-center gap-1 overflow-x-auto py-2 -mb-px" style={{ scrollbarWidth: 'none' }}>
          {LINKS.map((l) => (
            <li key={l.id}>
              <a
                href={`#${l.id}`}
                aria-current={active === l.id ? 'true' : undefined}
                className={`block whitespace-nowrap px-3 py-1.5 rounded-md text-[12.5px] font-medium transition-colors ${
                  active === l.id
                    ? 'bg-[rgba(99,102,241,0.12)] text-[#818cf8]'
                    : 'text-[#6b7683] hover:text-[#a5b0bd] hover:bg-white/[0.04]'
                }`}
              >
                {l.label}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  )
}
