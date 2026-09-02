/**
 * RAGAnalysis.jsx — Part C of Week 4 (Exercise 5)
 *
 * Shows how retrieval quality affects generation quality, using real
 * question→context→response traces from the evaluation run.
 *
 * 6 cases as required:
 *   A. Relevant retrieval → correct answer
 *   B. Irrelevant retrieval → effect on answer
 *   C. Information missed → partial answer
 *   D. Correct answer despite imperfect retrieval
 *   E. Hallucination despite relevant context
 *   F. No information available → model should refuse
 */
import React, { useState } from 'react'
import Section from './ui/Section'

const CASES = [
  {
    id: 'A',
    label: 'Case A — Relevant retrieval, correct answer',
    verdict: 'Retrieval succeeded',
    verdictTone: 'good',
    model: 'llama3.2:latest',
    question: 'What happens if a borrower defaults on a secured loan?',
    qid: 'F03',
    category: 'factual_retrieval',
    chunks: [
      { source: 'loan_risks.txt', distance: 0.201, text: 'Secured loans carry collateral risk. If the borrower defaults, the lender may be able to repossess or sell the pledged asset according to the agreement and applicable law. Unsecured loans may not involve collateral, but default can still harm credit history and lead to collection...' },
      { source: 'loans.txt', distance: 0.482, text: '...a house, car, deposit, or other asset. If the borrower does not repay, the lender may have a legal claim on the collateral. An unsecured loan does not use collateral, so lenders rely more heavily on the borrower\'s income, credit history, and repayment capacity...' },
      { source: 'loan_repayment.txt', distance: 0.591, text: '...payment can lead to late fees, penalty interest, credit score impact, collection activity, or legal consequences depending on the loan agreement...' },
    ],
    response: 'According to the provided context, if a borrower defaults on a secured loan, the lender may be able to repossess or sell the pledged asset (such as a house, car, or deposit) according to the agreement and applicable law.',
    analysis: [
      { type: 'good', text: 'Expected source loan_risks.txt retrieved at rank 1 with low L2 distance (0.201). The answer chunk contains the direct response almost verbatim.' },
      { type: 'good', text: 'Key facts matched: 3/3 (repossess, sell, pledged asset). Groundedness: 100% — every content word traces to supplied context.' },
      { type: 'info', text: 'This is the pipeline behaving as designed: good retrieval → good context → correct grounded answer.' },
    ],
    retrievalQuality: 'high',
    answerQuality: 'correct',
    hallucinated: false,
  },
  {
    id: 'B',
    label: 'Case B — Irrelevant retrieval returned',
    verdict: 'Retrieval failed — 3 of 3 chunks irrelevant',
    verdictTone: 'bad',
    model: 'codellama:7b vs llama3.2:latest',
    question: 'What is the capital city of Australia?',
    qid: 'H04',
    category: 'out_of_kb',
    chunks: [
      { source: 'loans.txt', distance: 0.972, text: 'A loan is money borrowed from a lender and repaid over time, usually with interest. The borrower receives funds upfront and agrees to repay the principal plus borrowing costs according to a schedule...' },
      { source: 'loan_eligibility.txt', distance: 1.089, text: 'Loan eligibility is the lender\'s assessment of whether a borrower can responsibly repay. Lenders commonly review income, employment stability, existing debt, credit history...' },
      { source: 'loan_risks.txt', distance: 1.134, text: 'Loans create repayment obligations, so borrowers should understand the risks before accepting funds...' },
    ],
    response: 'codellama: "Canberra" (fabricated from parametric memory)\nllama3.2: "This information is not available in my knowledge base."',
    analysis: [
      { type: 'bad', text: 'FAISS IndexFlatL2 with top_k=3 always returns exactly 3 chunks — there is no distance threshold. The nearest chunk sits at L2 0.972, versus 0.201 for a genuine hit. Still retrieved and injected into the prompt.' },
      { type: 'bad', text: 'codellama answered from parametric memory (Canberra) — a factual fabrication. llama3.2 correctly refused. Same bad retrieval, opposite outcomes.' },
      { type: 'info', text: 'This is the structural finding: the retriever cannot abstain. Adding a distance threshold would convert both models to a clean refusal, rather than relying on the model being well-behaved.' },
    ],
    retrievalQuality: 'irrelevant',
    answerQuality: 'model-dependent',
    hallucinated: true,
  },
  {
    id: 'C',
    label: 'Case C — Important information missed',
    verdict: 'Retrieval incomplete — expected source absent from top-3',
    verdictTone: 'warn',
    model: 'llama3.2:latest',
    question: 'I want to borrow money for a car. Which loan type applies and what should I check before accepting it?',
    qid: 'S02',
    category: 'multi_doc_synthesis',
    chunks: [
      { source: 'loans.txt', distance: 0.441, text: 'A loan is money borrowed from a lender and repaid over time, usually with interest. Common loan types include personal loans, home loans or mortgages, auto loans, education loans, and business loans...' },
      { source: 'loan_eligibility.txt', distance: 0.512, text: '...property papers for secured loans, and vehicle or education documents for specific loan types...' },
      { source: 'loan_eligibility.txt', distance: 0.528, text: 'Loan eligibility is the lender\'s assessment of whether a borrower can responsibly repay. Lenders commonly review income, employment stability, existing debt...' },
    ],
    response: 'Based on the context provided, an auto loan is a common type of loan used to purchase a vehicle. Before accepting the loan, you should check the total cost (not just the EMI), interest rate, fees, and your repayment capacity. [Note: loan_types.txt with specific auto loan details was not retrieved]',
    analysis: [
      { type: 'bad', text: 'Expected loan_types.txt (which contains "Auto loans are used to buy vehicles and are commonly secured by the vehicle") was not in top-3. This is one of two Recall@3 misses in the entire run.' },
      { type: 'bad', text: 'The question has two intents: which loan type + what to check. A single 384-dim embedding averages both, landing between two documents and matching neither strongly.' },
      { type: 'info', text: 'All four models failed this question identically. This is a retrieval ceiling — no model can recover information the retriever never supplied.' },
    ],
    retrievalQuality: 'incomplete',
    answerQuality: 'partial',
    hallucinated: false,
  },
  {
    id: 'D',
    label: 'Case D — Correct answer despite imperfect retrieval',
    verdict: 'Answer correct despite synthesis being required',
    verdictTone: 'good',
    model: 'llama3.2:latest',
    question: 'Explain the difference between simple interest and compound interest.',
    qid: 'C02',
    category: 'conceptual',
    chunks: [
      { source: 'loan_interest.txt', distance: 0.198, text: 'Simple interest is calculated on the original principal. Compound interest can add unpaid interest to the balance, causing interest to be charged on interest. Many installment loans use an amortization schedule...' },
      { source: 'loan_interest.txt', distance: 0.251, text: 'Loan interest is the cost of borrowing money. A fixed interest rate stays the same during the loan period...' },
      { source: 'loan_interest.txt', distance: 0.389, text: 'In the early part of an amortized loan, a larger share of each payment often goes toward interest. Over time, as the outstanding balance falls, more of each payment goes toward reducing principal...' },
    ],
    response: 'Simple interest is calculated on the original principal amount only. Compound interest, on the other hand, adds unpaid interest to the balance, causing interest to accrue on interest — this means the effective cost grows over time as the balance increases.',
    analysis: [
      { type: 'good', text: 'loan_interest.txt returned at rank 1, L2 0.198. Context states the two types separately but never contrasts them — the model constructed the comparison.' },
      { type: 'good', text: 'Key facts: 3/3 matched. Groundedness: 92%. Relevance: 0.743. The model did genuine synthesis but every element traces back to supplied text.' },
      { type: 'info', text: 'Useful synthesis is not the same as invention. This distinguishes "good LLM reasoning from context" from hallucination — exactly what the groundedness metric measures.' },
    ],
    retrievalQuality: 'high',
    answerQuality: 'correct',
    hallucinated: false,
  },
  {
    id: 'E',
    label: 'Case E — Hallucination despite relevant context',
    verdict: 'Retrieval succeeded — model added unsupported facts anyway',
    verdictTone: 'bad',
    model: 'wizardlm2:7b',
    question: 'Which documents are usually requested for a loan application?',
    qid: 'F06',
    category: 'factual_retrieval',
    chunks: [
      { source: 'loan_eligibility.txt', distance: 0.189, text: '...property papers for secured loans, and vehicle or education documents for specific loan types...' },
      { source: 'loan_eligibility.txt', distance: 0.224, text: 'Documents requested for loan applications often include identity proof, address proof, income proof, bank statements, tax documents, employment details, property papers for secured loans...' },
      { source: 'loan_eligibility.txt', distance: 0.301, text: 'Loan eligibility is the lender\'s assessment of whether a borrower can responsibly repay. Lenders commonly review income, employment stability, existing debt, credit history...' },
    ],
    response: 'For a loan application, you will typically need: identity proof (e.g. passport, driver\'s license, Social Security Number), address proof, income proof (e.g. W-2 forms, pay stubs), bank statements, tax returns, employment details, and property papers for secured loans.',
    analysis: [
      { type: 'bad', text: 'Retrieval was correct: loan_eligibility.txt at rank 1, L2 0.189. Context lists precisely the document categories asked about — no US-specific documents mentioned.' },
      { type: 'bad', text: 'WizardLM added "W-2 forms", "Social Security Number", "driver\'s license" — US instruments that do not exist in the knowledge base, which is jurisdiction-neutral. An Indian borrower would be told to produce documents that don\'t apply to them.' },
      { type: 'bad', text: 'The answer passed the accuracy check (facts_matched: 5/5) yet groundedness was only 56%. This is the dangerous failure mode: wrapped inside a correct answer, passing accuracy metrics, detectable only via groundedness.' },
    ],
    retrievalQuality: 'high',
    answerQuality: 'embellished',
    hallucinated: true,
  },
  {
    id: 'F',
    label: 'Case F — No information available in knowledge base',
    verdict: 'Out-of-scope question — model should refuse',
    verdictTone: 'neutral',
    model: 'gemma:2b vs codellama:7b',
    question: 'What is the current repo rate set by the Reserve Bank of India?',
    qid: 'H02',
    category: 'out_of_kb',
    chunks: [
      { source: 'loan_interest.txt', distance: 0.834, text: 'Loan interest is the cost of borrowing money. It is usually expressed as an annual percentage rate. A fixed interest rate stays the same during the loan period, while a variable or floating interest rate can change based on a benchmark or lender policy...' },
      { source: 'loan_eligibility.txt', distance: 0.901, text: 'Credit score is one factor in many loan decisions. A higher score can indicate lower repayment risk...' },
      { source: 'loans.txt', distance: 0.957, text: 'A loan is money borrowed from a lender and repaid over time, usually with interest...' },
    ],
    response: 'gemma:2b: "This information is not available in my knowledge base." ✓ Correct refusal\ncodellama:7b: "The current repo rate set by the RBI is 6.5%" ✗ Fabricated — this specific rate is not in any KB document',
    analysis: [
      { type: 'good', text: 'Gemma 2B correctly refused with the fallback phrase. Llama 3.2 also refused correctly.' },
      { type: 'bad', text: 'Code Llama fabricated a specific rate (6.5%) not present in any knowledge base document, answering a current-events question from parametric memory.' },
      { type: 'info', text: 'This is the most dangerous failure for a lending assistant: quoting a specific financial figure with authority when the KB contains no such data.' },
    ],
    retrievalQuality: 'irrelevant',
    answerQuality: 'model-dependent',
    hallucinated: true,
  },
]

const TONE_STYLES = {
  good:    { badge: 'border-green-500/30 bg-green-500/10 text-green-300', dot: 'bg-green-400' },
  warn:    { badge: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300', dot: 'bg-yellow-400' },
  bad:     { badge: 'border-red-500/30 bg-red-500/10 text-red-300', dot: 'bg-red-400' },
  neutral: { badge: 'border-white/20 bg-white/[0.04] text-[#a5b0bd]', dot: 'bg-slate-400' },
}

const QUALITY_BADGE = {
  high:           { label: 'High quality retrieval', cls: 'text-green-400 border-green-500/30 bg-green-500/10' },
  incomplete:     { label: 'Incomplete retrieval', cls: 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10' },
  irrelevant:     { label: 'Irrelevant retrieval', cls: 'text-red-400 border-red-500/30 bg-red-500/10' },
}

const ANALYSIS_STYLES = {
  good: 'text-green-300',
  bad:  'text-red-300',
  info: 'text-[#a5b0bd]',
  warn: 'text-yellow-300',
}

const ANALYSIS_ICONS = { good: '✓', bad: '✗', info: 'ℹ', warn: '⚠' }

export default function RAGAnalysis() {
  const [activeCase, setActiveCase] = useState('A')
  const c = CASES.find(x => x.id === activeCase)

  return (
    <Section
      id="rag-analysis"
      eyebrow="Part C — Week 4 · Exercise 5"
      title="🔍 RAG Pipeline Analysis"
      description="How retrieval quality shapes generation quality. Each case uses real traces from the 116-evaluation run."
    >
      {/* ── Retrieval baseline ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          ['Recall@3', '89.5%', 'top-3 hits / total'],
          ['MRR', '0.895', 'mean reciprocal rank'],
          ['Retrieval Misses', '2 / 19', 'S02, C04'],
          ['Top-K', '3', 'all models, same index'],
        ].map(([l, v, s]) => (
          <div key={l} className="panel p-3 text-center">
            <p className="text-xl font-bold text-[#818cf8]">{v}</p>
            <p className="text-[11.5px] text-[#a5b0bd] mt-0.5">{l}</p>
            <p className="text-[10px] text-[#6b7683] font-mono mt-0.5">{s}</p>
          </div>
        ))}
      </div>

      {/* ── Case selector ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2 mb-5">
        {CASES.map(cs => {
          const styles = TONE_STYLES[cs.verdictTone]
          return (
            <button
              key={cs.id}
              onClick={() => setActiveCase(cs.id)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[12.5px] font-medium transition-colors
                ${activeCase === cs.id
                  ? `${styles.badge}`
                  : 'border-white/10 bg-white/[0.02] text-[#6b7683] hover:border-white/20 hover:text-[#a5b0bd]'
                }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${activeCase === cs.id ? styles.dot : 'bg-white/20'}`} />
              Case {cs.id}
            </button>
          )
        })}
      </div>

      {/* ── Case detail ───────────────────────────────────────────────────── */}
      {c && (
        <div className="space-y-4">
          <div className="panel p-4">
            <div className="flex flex-wrap items-start gap-3 mb-3">
              <h3 className="text-[14px] font-semibold text-[#f1f5f9] flex-1">{c.label}</h3>
              <span className={`text-[11.5px] px-2.5 py-1 rounded border font-medium ${TONE_STYLES[c.verdictTone].badge}`}>
                {c.verdict}
              </span>
            </div>
            <div className="flex flex-wrap gap-2 text-[11.5px]">
              <span className="px-2 py-0.5 border border-white/10 bg-white/[0.04] rounded font-mono text-[#6b7683]">
                {c.qid} · {c.category}
              </span>
              <span className="px-2 py-0.5 border border-white/10 bg-white/[0.04] rounded font-mono text-[#6b7683]">
                model: {c.model}
              </span>
              {QUALITY_BADGE[c.retrievalQuality] && (
                <span className={`px-2 py-0.5 border rounded text-[11px] font-medium ${QUALITY_BADGE[c.retrievalQuality].cls}`}>
                  {QUALITY_BADGE[c.retrievalQuality].label}
                </span>
              )}
            </div>
          </div>

          {/* Question */}
          <div className="panel p-4">
            <p className="text-[11px] uppercase tracking-widest text-[#6b7683] mb-2">Question</p>
            <p className="text-[14px] text-[#f1f5f9] font-medium">"{c.question}"</p>
          </div>

          {/* Retrieved context */}
          <div className="panel p-4">
            <p className="text-[11px] uppercase tracking-widest text-[#6b7683] mb-3">Retrieved Context (top 3)</p>
            <div className="space-y-2">
              {c.chunks.map((chunk, i) => (
                <div key={i} className="bg-[#0a0a0f] border border-white/[0.08] rounded-lg p-3">
                  <div className="flex flex-wrap items-center gap-2 mb-1.5">
                    <span className="text-[11.5px] font-semibold text-orange-400">Rank {i + 1}</span>
                    <span className="font-mono text-[11px] text-[#6b7683]">{chunk.source}</span>
                    <span className="text-[11px] text-[#6b7683]">
                      L2: <span className={`font-mono font-medium ${chunk.distance < 0.5 ? 'text-green-400' : chunk.distance < 0.8 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {chunk.distance.toFixed(3)}
                      </span>
                    </span>
                    {chunk.distance > 0.8 && (
                      <span className="text-[10px] px-1.5 py-0.5 border border-red-500/30 bg-red-500/10 text-red-400 rounded">
                        poor match
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#cbd5e1] leading-relaxed">{chunk.text}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Response */}
          <div className="panel p-4">
            <p className="text-[11px] uppercase tracking-widest text-[#6b7683] mb-3">LLM Response</p>
            <div className={`p-3.5 rounded-lg border whitespace-pre-line text-sm leading-relaxed ${
              c.hallucinated
                ? 'border-red-500/30 bg-red-500/5 text-[#f1f5f9]'
                : 'border-teal-500/30 bg-teal-500/5 text-white'
            }`}>
              {c.response}
            </div>
          </div>

          {/* Analysis */}
          <div className="panel p-4">
            <p className="text-[11px] uppercase tracking-widest text-[#6b7683] mb-3">Analysis</p>
            <div className="space-y-2.5">
              {c.analysis.map((a, i) => (
                <div key={i} className="flex gap-2.5">
                  <span className={`text-sm font-bold mt-0.5 shrink-0 ${ANALYSIS_STYLES[a.type]}`}>
                    {ANALYSIS_ICONS[a.type]}
                  </span>
                  <p className={`text-[12.5px] leading-relaxed ${ANALYSIS_STYLES[a.type]}`}>{a.text}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Chain summary ─────────────────────────────────────────────────── */}
      <div className="mt-6 panel p-4">
        <p className="text-[12.5px] font-semibold text-[#f1f5f9] mb-3">Retrieval → Context → Response: the chain is necessary but not sufficient</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[540px] text-[12px]">
            <thead>
              <tr className="border-b border-white/10">
                {['Retrieval', 'Context', 'Response', 'Case'].map(h => (
                  <th key={h} className="py-2 pr-4 text-left text-[11px] text-[#6b7683] uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                ['Expected source, rank 1, low L2', 'Sufficient, on-topic', 'Correct and grounded', 'A, D'],
                ['Nothing relevant — 3 chunks returned anyway', 'Actively misleading', 'Model-dependent: refusal or fabrication', 'B, F'],
                ['Expected source outside top-3', 'Incomplete', 'Partial — an unrecoverable ceiling', 'C'],
                ['Expected source, rank 1, low L2', 'Sufficient', 'Still embellished with outside facts', 'E'],
              ].map((row, i) => (
                <tr key={i} className="border-b border-white/[0.05]">
                  {row.map((cell, j) => (
                    <td key={j} className={`py-2.5 pr-4 leading-relaxed ${j === 3 ? 'font-mono text-[#818cf8] font-semibold' : 'text-[#a5b0bd]'}`}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[11.5px] text-[#6b7683] mt-3">
          Cases B and E break the naive assumption that good retrieval guarantees a good answer. Context quality constrains response quality; it does not determine it.
        </p>
      </div>
    </Section>
  )
}
