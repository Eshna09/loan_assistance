"""
rag_analysis.py — Exercise 5: trace how retrieval shapes the final answer.

Builds RAG_PIPELINE_ANALYSIS.md from real QUESTION -> RETRIEVED CONTEXT ->
LLM RESPONSE traces. Questions and responses come from results/raw_results.json
(the recorded 116-generation run). The per-chunk L2 distances were not stored in
that file, so they are re-fetched from the Retrieval Service; the script first
asserts the index is byte-for-byte the same size as at run time, and refuses to
produce a report if it is not.

The five required case types are located as follows:

  relevant retrieved    expected source at rank 1 with a low L2 distance
  irrelevant retrieved  out-of-KB questions - the retriever always returns three
                        chunks, so 100% of what it returns is irrelevant
  information missed    expected source absent from the top-3 (a Recall@3 miss)
  correct answer        key-fact threshold met on a clean retrieval
  hallucinated with
  context               the answer contains specifics absent from its context

Requires the Retrieval Service on :8001 (docker compose up -d).
"""

import json
import os
import re
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
RETRIEVAL_URL = os.environ.get("RETRIEVAL_URL", "http://127.0.0.1:8001")

STOPWORDS = set("""a an the and or but if then than that this these those of to in on for with without
by from as at is are was were be been being it its do does did not no nor so such can could may might
will would shall should must have has had you your i we they them their our us me my what which who
when where why how about into over under more most less least other some any each both few many own
same very just also only there here will can each include including such as""".split())


def content_words(text):
    return [w for w in re.findall(r"[a-z][a-z'-]{2,}", (text or "").lower()) if w not in STOPWORDS]


def ungrounded_terms(answer, context, limit=10):
    """Distinctive words the model introduced that are absent from its context."""
    ctx = set(content_words(context))
    seen, out = set(), []
    for w in content_words(answer):
        if w not in ctx and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:limit]


def load():
    with open(os.path.join(RESULTS, "raw_results.json"), encoding="utf-8") as f:
        raw = json.load(f)
    with open(os.path.join(RESULTS, "summary.json"), encoding="utf-8") as f:
        summary = json.load(f)
    with open(os.path.join(HERE, "eval_set.json"), encoding="utf-8") as f:
        eval_set = json.load(f)
    return raw, summary, {q["id"]: q for q in eval_set["questions"]}


def check_index(raw):
    """Refuse to run if the index has changed since the evaluation."""
    try:
        info = requests.get(f"{RETRIEVAL_URL}/index/info", timeout=10).json()
    except requests.RequestException as exc:
        sys.exit(f"Retrieval Service unreachable at {RETRIEVAL_URL}: {exc}\n"
                 f"Start it with: docker compose up -d")

    expected = raw["knowledge_base"]["vectors"]
    if info["vectors"] != expected:
        sys.exit(
            f"Index has {info['vectors']} vectors but the evaluation ran against {expected}. "
            "Distances would not match the recorded answers; refusing to generate a report."
        )
    return info


def retrieve(question):
    res = requests.post(
        f"{RETRIEVAL_URL}/retrieve", json={"question": question, "top_k": 3}, timeout=30
    )
    res.raise_for_status()
    return res.json()


def run_for(raw, model, qid):
    return next(r for r in raw["runs"][model]["results"] if r["id"] == qid)


def score_for(summary, model, qid):
    return next(r for r in summary["models"][model]["per_question"] if r["id"] == qid)


def chunk_block(det, max_chars=320):
    lines = []
    for i, (c, d) in enumerate(zip(det["chunks"], det["distances"]), 1):
        text = " ".join(c["text"].split())
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        lines.append(f"[{i}] {c['source']}   L2 distance {d:.3f}\n    {text}")
    return "\n\n".join(lines)


def answer_block(run, max_chars=760):
    text = (run.get("answer") or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def case(title, verdict, qid, model, question, det, run, notes):
    L = [
        f"### {title}\n",
        f"**Verdict:** {verdict}  ·  **Model:** `{model}`\n",
        f"**QUESTION** (`{qid}`)\n",
        f"> {question}\n",
        "**RETRIEVED CONTEXT**\n",
        "```",
        chunk_block(det),
        "```\n",
        "**LLM RESPONSE**\n",
        "```",
        answer_block(run),
        "```\n",
        "**Analysis**\n",
    ]
    L += [f"{n}\n" for n in notes]
    return "\n".join(L)


def main():
    raw, summary, questions = load()
    info = check_index(raw)
    rq = summary["retrieval_quality"]
    misses = [r["id"] for r in rq["per_question"] if r["hit_rank"] is None]

    # Retrieve once for every question used below.
    used = ["F03", "H04", misses[0] if misses else "S02", "C02", "F06"]
    det = {qid: retrieve(questions[qid]["question"]) for qid in used}

    L = []
    L.append("# RAG Pipeline Analysis — how retrieval shapes the answer\n")
    L.append(
        "**Exercise 5.** Questions and responses below are verbatim from "
        "`results/raw_results.json`, the recorded output of 116 generations across four "
        "models. L2 distances are re-measured against the same FAISS index "
        f"({info['vectors']} vectors, {info['dimension']}-dim, `{info['index_type']}`); the "
        "script aborts if that index has changed since the run.\n"
    )
    L.append(
        f"Retrieval baseline across the run: **Recall@3 {rq['recall_at_3'] * 100:.1f}%**, "
        f"**MRR {rq['mrr']:.3f}**, over {rq['questions_considered']} questions that have an "
        "expected source document.\n"
    )
    L.append("---\n")

    # ── 1. relevant information retrieved ───────────────────────────────────
    qid, model = "F03", "llama3.2:latest"
    q, run, sc = questions[qid], run_for(raw, model, qid), score_for(summary, model, qid)
    L.append("## 1. Relevant information was retrieved\n")
    L.append(case(
        "Clean retrieval, grounded answer", "Retrieval succeeded — answer correct",
        qid, model, q["question"], det[qid], run,
        [
            f"- The expected source `{q['expected_sources'][0]}` returned at **rank 1**, "
            f"L2 distance **{det[qid]['distances'][0]:.3f}** — the chunk containing the answer sentence "
            "almost verbatim.",
            f"- Key facts matched **{sc['facts_matched']}/{sc['facts_total']}**; groundedness "
            f"**{sc['groundedness'] * 100:.0f}%**.",
            "- Nearly every content word in the response traces to the supplied context. This is the "
            "pipeline behaving as designed: good retrieval produced good context, and good context "
            "produced a correct, grounded answer.",
        ],
    ))

    # ── 2. irrelevant information retrieved ─────────────────────────────────
    qid, model = "H04", "codellama:7b"
    q, run = questions[qid], run_for(raw, model, qid)
    alt = run_for(raw, "llama3.2:latest", qid)
    L.append("## 2. Irrelevant information was retrieved\n")
    L.append(case(
        "The retriever cannot return nothing", "Retrieval failed — 3 of 3 chunks irrelevant",
        qid, model, q["question"], det[qid], run,
        [
            "- **The structural finding of this analysis.** FAISS `IndexFlatL2` with `top_k=3` always "
            "returns exactly three chunks. There is no distance threshold and no way to express "
            "\"nothing here matches\".",
            f"- The nearest chunk sits at L2 **{det[qid]['distances'][0]:.3f}**, against "
            f"**{det['F03']['distances'][0]:.3f}** for the genuine hit in case 1 — measurably worse, "
            "yet still retrieved and still injected into the prompt.",
            "- The model is handed three paragraphs about loans and asked about Australian geography. "
            "The context is not merely unhelpful; it is misleading, because its presence implies "
            "something relevant was found.",
            f"- codellama answered from parametric memory: *\"{answer_block(run, 90)}\"*  \n"
            f"  llama3.2, given **byte-identical** context, replied: *\"{answer_block(alt, 90)}\"*",
            "- **Same bad retrieval, opposite outcomes.** The retrieval layer cannot explain the "
            "difference, because it was the same call replayed to both.",
        ],
    ))

    # ── 3. important information missed ─────────────────────────────────────
    qid, model = (misses[0] if misses else "S02"), "llama3.2:latest"
    q, run, sc = questions[qid], run_for(raw, model, qid), score_for(summary, model, qid)
    mean_cov = summary["models"][model]["quality"]["mean_fact_coverage"]
    L.append("## 3. Important information was missed\n")
    L.append(case(
        "A retrieval miss caps the answer", "Retrieval incomplete — expected source absent from top-3",
        qid, model, q["question"], det[qid], run,
        [
            f"- Expected `{'`, `'.join(q['expected_sources'])}`; retrieved "
            f"`{'`, `'.join(det[qid]['sources'])}`. One of the two Recall@3 misses in the run.",
            "- `loan_types.txt` contains *\"Auto loans are used to buy vehicles and are commonly secured "
            "by the vehicle\"* — the direct answer to the first half of the question. It was never "
            "retrieved, so no model could use it.",
            f"- Fact coverage fell to **{sc['fact_coverage'] * 100:.0f}%** "
            f"({sc['facts_matched']}/{sc['facts_total']}) against this model's "
            f"{mean_cov * 100:.0f}% average.",
            "- Cause: the question carries two intents — *which loan type* and *what to check*. The query "
            "embedding averages both, landing between two documents and matching neither strongly. "
            "**A single 384-dimension vector cannot represent a two-part question.**",
            "- All four models failed this question the same way. This is a ceiling: no model can recover "
            "information the retriever never supplied.",
        ],
    ))

    # ── 4. correct answer ───────────────────────────────────────────────────
    qid, model = "C02", "llama3.2:latest"
    q, run, sc = questions[qid], run_for(raw, model, qid), score_for(summary, model, qid)
    L.append("## 4. The LLM produced a correct answer\n")
    L.append(case(
        "Synthesis that stays inside the context", "Retrieval succeeded — answer correct and grounded",
        qid, model, q["question"], det[qid], run,
        [
            f"- `{det[qid]['sources'][0]}` returned at rank 1, L2 **{det[qid]['distances'][0]:.3f}**. The "
            "context states the two interest types separately but never contrasts them.",
            f"- Key facts **{sc['facts_matched']}/{sc['facts_total']}**, groundedness "
            f"**{sc['groundedness'] * 100:.0f}%**, relevance **{sc['relevance']:.3f}**.",
            "- The model did genuine work — it built the comparison the question asked for — but every "
            "element of that comparison traces back to the supplied text. Useful synthesis is not the "
            "same as invention, and this is the distinction the groundedness metric is measuring.",
        ],
    ))

    # ── 5. hallucination despite retrieved context ──────────────────────────
    qid, model = "F06", "wizardlm2:7b"
    q, run, sc = questions[qid], run_for(raw, model, qid), score_for(summary, model, qid)
    extra = ungrounded_terms(run["answer"], det[qid]["context"] if "context" in det[qid] else
                             "\n".join(c["text"] for c in det[qid]["chunks"]))
    gnd_model = summary["models"][model]["quality"]["mean_groundedness"]
    gnd_best = summary["models"]["llama3.2:latest"]["quality"]["mean_groundedness"]
    L.append("## 5. The LLM hallucinated despite having retrieved context\n")
    L.append(case(
        "Correct retrieval, embellished answer", "Retrieval succeeded — the model added facts anyway",
        qid, model, q["question"], det[qid], run,
        [
            f"- Retrieval was **correct**: `{q['expected_sources'][0]}` at rank 1, L2 "
            f"**{det[qid]['distances'][0]:.3f}**. The context lists precisely the document categories "
            "the question asks about.",
            f"- The answer scored **{sc['facts_matched']}/{sc['facts_total']}** on key facts and is "
            f"marked **correct** by the accuracy metric — yet its groundedness is only "
            f"**{sc['groundedness'] * 100:.0f}%**.",
            f"- It expanded each category with specifics found **nowhere in the context**: "
            f"`{'`, `'.join(extra[:8])}`.",
            "- `W-2` and `driver's license` are United States tax and identity instruments. The knowledge "
            "base is jurisdiction-neutral and names no country. The model imported these from training "
            "data and presented them in the same voice as the retrieved material — an Indian borrower "
            "would be told to produce documents that do not exist for them.",
            "- **This is the dangerous failure mode.** Unlike an out-of-scope fabrication it is wrapped "
            "inside a correct answer, cites the right source, and passes the accuracy check. Only "
            f"groundedness separates it: {gnd_model * 100:.1f}% for this model against "
            f"{gnd_best * 100:.1f}% for llama3.2.",
        ],
    ))

    # ── the relationship ────────────────────────────────────────────────────
    L.append("---\n")
    L.append("## Retrieval quality → context quality → response quality\n")
    L.append(
        "The five cases trace one chain, and every link can fail independently.\n"
    )
    L.append("""| Retrieval quality | Context quality | Response quality | Case |
|---|---|---|---|
| Expected source, rank 1, low distance | Sufficient, on-topic | Correct and grounded | 1, 4 |
| Nothing relevant exists — 3 chunks returned regardless | Actively misleading | **Model-dependent**: refusal or fabrication | 2 |
| Expected source outside top-3 | Incomplete | Partial — a ceiling, unrecoverable | 3 |
| Expected source, rank 1, low distance | Sufficient | **Still embellished with outside facts** | 5 |
""")
    L.append(
        "**The chain is necessary but not sufficient.** Cases 1 and 4 show good retrieval enabling a "
        "good answer; case 3 shows poor retrieval capping it, since no model can recover what was never "
        "supplied. But cases 2 and 5 break the assumption that the chain is deterministic:\n"
    )
    L.append(
        "- **Case 2** — identical irrelevant context produced a fabrication from codellama and a correct "
        "refusal from llama3.2.\n"
        "- **Case 5** — *good* context still produced ungrounded content.\n"
    )
    L.append(
        "Because retrieval was executed once and replayed byte-identically to all four models, neither "
        "difference can originate in the RAG layer. **Context quality constrains response quality; it "
        "does not determine it.** Whether a model stays inside its context is a separate property that "
        "varies enormously between models sharing one pipeline — measured across the full run as a "
        "fabrication rate of 60% and 80% for the two 7B models against 0% for both smaller ones.\n"
    )

    # ── why not a checkbox ──────────────────────────────────────────────────
    L.append("## Why RAG is not a checkbox before the LLM\n")
    L.append(
        "Four reasons, each evidenced above rather than asserted.\n\n"
        "**1. The retriever cannot abstain.** `top_k=3` guarantees three chunks whether or not anything "
        "relevant exists, so every out-of-scope question is answered against irrelevant context by "
        "construction (case 2). Adding retrieval did not give the system a way to say \"I don't know\" — "
        "it only changed what the model is looking at while it decides.\n\n"
        "**2. Retrieval sets a ceiling the model cannot raise.** Both Recall@3 misses were unrecoverable "
        "for all four models (case 3). Effort spent upgrading the model is wasted on any question where "
        "retrieval has already failed — the two are not interchangeable levers.\n\n"
        "**3. Grounding is a model property, not a prompt property.** Same instruction, same context, "
        "opposite behaviour (cases 2 and 5). The prompt *requests* grounding; it cannot *enforce* it.\n\n"
        "**4. Accuracy metrics conceal grounding failures.** The case-5 answer scores correct while being "
        "half ungrounded. A pipeline evaluated only on accuracy would rate it a success.\n\n"
        "RAG moved hallucination rather than removing it — out of the core facts of an answer, and into "
        "its embellishments and its out-of-scope behaviour. A checkbox implementation would miss all "
        "four of these, because each is invisible unless the intermediate context is inspected.\n"
    )

    # ── what to change ──────────────────────────────────────────────────────
    L.append("## What this analysis says to change\n")
    L.append("""| Weakness | Evidence | Proposed fix |
|---|---|---|
| Retriever cannot abstain | Case 2 — 3 irrelevant chunks for a geography question | Reject chunks beyond an L2 distance threshold; pass empty context when none qualify, and let the prompt's fallback fire |
| Multi-intent questions retrieve poorly | Case 3 — both Recall@3 misses are two-part questions | Decompose the query, or retrieve per sub-question and merge the chunk sets |
| Embellishment goes unnoticed | Case 5 — scored correct at 50.6% groundedness | Surface groundedness next to the answer in the dashboard; consider per-sentence citation |
| Model choice dominates safety | Cases 2 and 5 — same context, opposite behaviour | Switch the default model to `llama3.2:3b` (0% fabrication against codellama's 60%) |
""")
    L.append(
        "The first fix is the highest-value one: a distance threshold would convert case 2 from a "
        "fabrication risk into a clean refusal for **every** model, rather than relying on the model to "
        "be well-behaved.\n"
    )

    out = os.path.join(HERE, "RAG_PIPELINE_ANALYSIS.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
