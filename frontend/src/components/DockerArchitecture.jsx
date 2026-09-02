import React from 'react'
import Section from './ui/Section'

const CONTAINERS = [
  {
    name: 'frontend',
    image: 'nginx:1.27-alpine',
    port: '3000 → 80',
    role: 'Serves the built dashboard, proxies /api/* to app-service',
  },
  {
    name: 'app-service',
    image: 'python:3.11-slim',
    port: '8000',
    role: 'Orchestration and the public API',
  },
  {
    name: 'retrieval-service',
    image: 'python:3.11-slim + torch (CPU)',
    port: '8001',
    role: 'MiniLM model baked into the image, FAISS index in memory',
  },
  {
    name: 'llm-service',
    image: 'python:3.11-slim',
    port: '8002',
    role: 'Wraps the Ollama runtime behind a stable contract',
  },
  {
    name: 'data-service',
    image: 'python:3.11-slim',
    port: '8003',
    role: 'Documents and uploads, backed by the kb-uploads volume',
  },
  {
    name: 'ollama',
    image: 'ollama/ollama:latest',
    port: '11435 → 11434',
    role: 'Code Llama runtime, models cached in the ollama-models volume',
  },
]

export default function DockerArchitecture() {
  return (
    <Section
      id="docker-architecture"
      eyebrow="Reference"
      title="Container topology"
      description="Six containers on one bridge network, addressing each other by service name."
      aside={<span className="chip font-mono">docker-compose.yml</span>}
    >

        {/* Topology */}
        <pre className="code-block text-[10.5px] mb-4">
{`  ┌─────────────────────── network: rag-net ───────────────────────┐
  │                                                                │
  │   frontend:80 ──/api/*──► app-service:8000                     │
  │                                │                               │
  │                                ├──► retrieval-service:8001     │
  │                                │            │                  │
  │                                │            └──► data-service  │
  │                                │                    :8003      │
  │                                └──► llm-service:8002           │
  │                                            │                   │
  │                                            └──► ollama:11434   │
  └────────────────────────────────────────────────────────────────┘

  volumes:  kb-uploads      → data-service:/data/uploaded_kb
            ollama-models   → ollama:/root/.ollama`}
        </pre>

        {/* Container cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {CONTAINERS.map((c) => (
            <div key={c.name} className="panel p-3.5">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-[12.5px] font-mono font-medium text-[#818cf8] truncate">{c.name}</p>
                <span className="text-[10.5px] font-mono tabular text-[#6b7683] shrink-0">{c.port}</span>
              </div>
              <p className="text-[11.5px] text-[#a5b0bd] mt-1.5 leading-relaxed">{c.role}</p>
              <p className="text-[10.5px] text-[#6b7683] font-mono mt-1.5 truncate">{c.image}</p>
            </div>
          ))}
        </div>

        {/* Commands */}
        <div className="mt-5 pt-4 border-t border-white/[0.07]">
          <p className="eyebrow mb-2">Bring the stack up</p>
          <pre className="code-block">
{`docker compose up --build -d
docker compose exec ollama ollama pull codellama:7b   # once, ~3.8 GB
docker compose ps
curl http://localhost:8000/health`}
          </pre>
          <p className="text-[11.5px] text-[#6b7683] mt-3 leading-relaxed">
            Ports 8000–8003 are published so each service can be called directly, which is how the
            service boundaries are demonstrated. Only the frontend on port 3000 is needed to use the
            app. GPU reservation for the Ollama container is included in the compose file, commented
            out — it requires the NVIDIA container toolkit.
          </p>
        </div>
    </Section>
  )
}
