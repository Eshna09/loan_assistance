import React from 'react'
import Section from './ui/Section'

export default function QueryHistory({ history, onRerun }) {
  if (!history || history.length === 0) return null

  return (
    <Section
      id="query-history"
      eyebrow="This session"
      title="Query history"
      compact
      aside={
        <span className="chip tabular">
          {history.length} {history.length === 1 ? 'query' : 'queries'}
        </span>
      }
    >
      <ul className="flex flex-col gap-1.5">
        {history.slice().reverse().map((item, i) => (
          <li
            key={i}
            className="group flex items-start gap-3 px-3 py-2.5 rounded-lg hover:bg-white/[0.04] transition-colors"
          >
            <span className="text-[11px] text-[#6b7683] font-mono tabular shrink-0 mt-1 w-5 text-right">
              {history.length - i}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-[13.5px] text-[#f1f5f9] truncate">{item.question}</p>
              {item.answer && (
                <p className="text-[12px] text-[#6b7683] mt-0.5 truncate">{item.answer}</p>
              )}
            </div>
            <button
              onClick={() => onRerun && onRerun(item.question)}
              className="btn btn-ghost text-[12px] shrink-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
            >
              Re-run
            </button>
          </li>
        ))}
      </ul>
    </Section>
  )
}
