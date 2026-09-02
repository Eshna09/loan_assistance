import React from 'react'
import Section from './ui/Section'

const SERVICES = [
  {
    endpoint: '/ask',
    name: 'Application Service',
    accepts: '{ "question": string }',
    returns: '{ "question", "answer", "sources" }',
    responsibilities: [
      'Receives the question',
      'Sequences retrieval then generation',
      'Returns the final response',
    ],
  },
  {
    endpoint: '/retrieve',
    name: 'Retrieval Service',
    accepts: '{ "question": string }',
    returns: '{ "context_chunks", "sources" }',
    responsibilities: [
      'Encodes the query with MiniLM',
      'Searches FAISS IndexFlatL2, top_k=3',
      'Returns chunks and source filenames',
    ],
  },
  {
    endpoint: '/generate',
    name: 'LLM Service',
    accepts: '{ "prompt": string }',
    returns: '{ "answer": string }',
    responsibilities: [
      'Forwards the prompt to Ollama',
      'model=codellama:7b, stream=false',
      'Returns the generated answer',
    ],
  },
  {
    endpoint: '/ask/debug',
    name: 'Debug endpoint',
    accepts: '{ "question": string }',
    returns: '{ embedding, chunks, distances, context, prompt, answer, trace }',
    responsibilities: [
      'Runs the full pipeline',
      'Exposes every intermediate value',
      'Drives the live demo above',
    ],
  },
]

const FLOW = [
  'Frontend (React / Vite)',
  'App Service  :8000',
  'Retrieval Service  :8001',
  'FAISS IndexFlatL2',
  'LLM Service  :8002',
  'Ollama  :11434',
  'Code Llama 7B',
]

export default function ApiArchitecture() {
  return (
    <Section
      id="api-architecture"
      eyebrow="Reference"
      title="API surface"
      description="Each endpoint owns one stage, so a stage can be exercised on its own."
    >
      <div className="grid sm:grid-cols-2 gap-2.5">
        {SERVICES.map((s) => (
          <div key={s.endpoint} className="panel p-4">
            <p className="text-[13px] font-mono font-semibold text-[#818cf8]">{s.endpoint}</p>
            <p className="text-[11.5px] text-[#6b7683] mb-2.5">{s.name}</p>

            <ul className="flex flex-col gap-1 mb-3">
              {s.responsibilities.map((r) => (
                <li key={r} className="text-[12px] text-[#a5b0bd] flex items-start gap-2">
                  <span className="text-white/20 mt-[3px] text-[9px]">●</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>

            <dl className="pt-2.5 border-t border-white/[0.07] flex flex-col gap-1">
              <div className="flex gap-2 text-[11px]">
                <dt className="text-[#6b7683] w-[52px] shrink-0">Accepts</dt>
                <dd className="font-mono text-[#a5b0bd] break-all">{s.accepts}</dd>
              </div>
              <div className="flex gap-2 text-[11px]">
                <dt className="text-[#6b7683] w-[52px] shrink-0">Returns</dt>
                <dd className="font-mono text-[#a5b0bd] break-all">{s.returns}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      <div className="mt-5">
        <p className="eyebrow mb-2.5">Request flow</p>
        <ol className="code-block flex flex-col items-center gap-0.5">
          {FLOW.map((label, i) => (
            <React.Fragment key={label}>
              {i > 0 && <li aria-hidden="true" className="text-white/15 leading-none">↓</li>}
              <li className={i === 0 || i === FLOW.length - 1 ? 'text-[#f1f5f9]' : 'text-[#a5b0bd]'}>
                {label}
              </li>
            </React.Fragment>
          ))}
        </ol>
      </div>
    </Section>
  )
}
