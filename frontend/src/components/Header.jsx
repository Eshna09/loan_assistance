import React from 'react'

// The stack, as plain text. These were eight differently-coloured badges, which
// spent the page's entire colour budget before any content appeared.
const STACK = ['FastAPI', 'MiniLM', 'FAISS', 'Ollama', 'Code Llama', 'Docker']

const STATUS = {
  checking: { cls: 'chip', dot: 'bg-yellow-400 animate-pulse', text: 'Checking' },
  online: { cls: 'chip chip-ok', dot: 'bg-[#34d399]', text: 'System online' },
  offline: { cls: 'chip chip-bad', dot: 'bg-[#f87171]', text: 'Backend offline' },
}

export default function Header({ status }) {
  const s = STATUS[status] || STATUS.checking

  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-[#0a0a0f]/90 backdrop-blur-md">
      <div className="max-w-[1240px] mx-auto px-5 sm:px-8 h-16 flex items-center justify-between gap-5">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-7 h-7 rounded-md bg-[#6366f1] flex items-center justify-center text-[13px] font-semibold text-white shrink-0">
            ₹
          </div>
          <div className="min-w-0">
            <h1 className="text-[15px] font-semibold tracking-tight leading-tight truncate">
              Loan Knowledge Assistance
            </h1>
            <p className="text-[11.5px] text-[#6b7683] leading-tight truncate">
              Retrieval-augmented answering over a local knowledge base
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4 shrink-0">
          <div className="hidden xl:flex items-center gap-2 text-[11.5px] text-[#6b7683]">
            {STACK.map((t, i) => (
              <React.Fragment key={t}>
                {i > 0 && <span className="text-white/15">·</span>}
                <span>{t}</span>
              </React.Fragment>
            ))}
          </div>
          <span className={s.cls}>
            <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
            {s.text}
          </span>
        </div>
      </div>
    </header>
  )
}
