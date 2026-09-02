"""
source_graph.py — answer provenance graph.

Turns one pipeline run into a directed graph that answers "where did this
answer come from?":

    question ──retrieved──► chunk ──belongs_to──► document

plus the two document-to-document relations the evidence layer already
computes:

    document ──conflict────► document   two sources assert different values
                                        for the same normalised field
    document ──supersedes──► document   version resolution picked one source
                                        over another

Layout is deliberately NOT computed here.  This module returns nodes and
edges; the dashboard decides where to draw them, the same way every other
panel receives data rather than pixels.

Edge strength
    similarity   1 / (1 + L2 distance) — monotonic in distance, bounded (0, 1]
    weight       that similarity rescaled so the closest chunk is 1.0, which is
                 what the dashboard maps to stroke width

Answer overlap
    `answer_overlap` is the fraction of the answer's content words that also
    appear in a given chunk (or document).  It is a lexical proxy for "how much
    of the answer this source could account for", not a causal attribution —
    chunks overlap, so the values across chunks do not sum to 1.  The same
    word-set and stopword list as validate_grounding() are used so the two
    numbers stay comparable.
"""

# _content_words is private to the evidence module but public within this
# package: sharing it keeps the stopword list and tokenisation identical to
# the grounding score, which is the whole point of reusing it.
from services.app_service.evidence import _content_words

# ── Node and edge kinds ────────────────────────────────────────────────────
NODE_QUESTION = "question"
NODE_CHUNK = "chunk"
NODE_DOCUMENT = "document"

EDGE_RETRIEVED = "retrieved"
EDGE_BELONGS_TO = "belongs_to"
EDGE_CONFLICT = "conflict"
EDGE_SUPERSEDES = "supersedes"

QUESTION_NODE_ID = "q"
TEXT_PREVIEW_CHARS = 180


# ── Identity helpers ───────────────────────────────────────────────────────
def _document_node_id(source: str) -> str:
    return f"doc:{source}"


def _unique_chunk_node_id(chunk: dict, rank: int, taken: set) -> str:
    """
    Stable id for a chunk node.

    FAISS returns distinct row ids so `chunk_id` is normally unique already;
    the rank suffix is a guard so a duplicate can never collapse two nodes
    into one and silently drop an edge.
    """
    base = f"chunk:{chunk.get('chunk_id', rank)}"
    node_id = base
    if node_id in taken:
        node_id = f"{base}#{rank}"
    taken.add(node_id)
    return node_id


def _overlap_fraction(answer_words: list, word_set: set) -> float | None:
    """Fraction of the answer's content words present in `word_set`."""
    if not answer_words:
        return None
    matched = sum(1 for w in answer_words if w in word_set)
    return round(matched / len(answer_words), 4)


# ── Graph construction ─────────────────────────────────────────────────────
def build_source_graph(
    *,
    question: str,
    chunks: list,
    distances: list,
    llm_chunk_count: int = 0,
    answer: str | None = None,
    conflict: dict | None = None,
    version_resolution: dict | None = None,
) -> dict:
    """
    Build the provenance graph for one pipeline run.

    `chunks` / `distances` are the wide retrieval set, in rank order.  The
    first `llm_chunk_count` of them are the ones that actually reached the
    prompt — the graph marks the rest as retrieved-but-unused so the dashboard
    can show what the model did and did not see.
    """
    answer_words = _content_words(answer or "")

    nodes: list[dict] = [{
        "id": QUESTION_NODE_ID,
        "type": NODE_QUESTION,
        "label": question,
        "retrieved_count": len(chunks),
        "used_by_llm_count": min(llm_chunk_count, len(chunks)),
    }]
    edges: list[dict] = []

    # ── Chunk nodes + question→chunk edges ─────────────────────────────────
    similarities = [1.0 / (1.0 + max(float(d), 0.0)) for d in distances]
    best_similarity = max(similarities) if similarities else 1.0

    taken_ids: set = set()
    chunk_nodes: list[dict] = []
    # Union of the words of every chunk that actually reached the prompt.
    llm_context_words: set = set()

    # Accumulated per document, so a document's overlap uses the union of the
    # words of every chunk retrieved from it rather than just its best chunk.
    doc_state: dict[str, dict] = {}

    for rank, (chunk, distance) in enumerate(zip(chunks, distances), start=1):
        node_id = _unique_chunk_node_id(chunk, rank, taken_ids)
        source = chunk.get("source", "unknown")
        text = chunk.get("text") or ""
        similarity = similarities[rank - 1]
        weight = round(similarity / best_similarity, 4) if best_similarity else 0.0
        used_by_llm = rank <= llm_chunk_count

        chunk_words = set(_content_words(text))
        overlap = _overlap_fraction(answer_words, chunk_words)
        if used_by_llm:
            llm_context_words |= chunk_words

        chunk_node = {
            "id": node_id,
            "type": NODE_CHUNK,
            "label": f"#{rank}",
            "rank": rank,
            "chunk_id": chunk.get("chunk_id", rank - 1),
            "source": source,
            "document_id": _document_node_id(source),
            "distance": round(float(distance), 4),
            "similarity": round(similarity, 4),
            "weight": weight,
            "used_by_llm": used_by_llm,
            "answer_overlap": overlap,
            "characters": len(text),
            "text_preview": text[:TEXT_PREVIEW_CHARS],
            "truncated": len(text) > TEXT_PREVIEW_CHARS,
            "version": chunk.get("version", "1.0"),
            "effective_date": chunk.get("effective_date"),
            "document_type": chunk.get("document_type", "general"),
            "loan_type": chunk.get("loan_type", "general"),
        }
        chunk_nodes.append(chunk_node)

        edges.append({
            "id": f"e:{QUESTION_NODE_ID}->{node_id}",
            "source": QUESTION_NODE_ID,
            "target": node_id,
            "type": EDGE_RETRIEVED,
            "rank": rank,
            "distance": chunk_node["distance"],
            "similarity": chunk_node["similarity"],
            "weight": weight,
            "used_by_llm": used_by_llm,
            "answer_overlap": overlap,
        })
        edges.append({
            "id": f"e:{node_id}->{chunk_node['document_id']}",
            "source": node_id,
            "target": chunk_node["document_id"],
            "type": EDGE_BELONGS_TO,
            "used_by_llm": used_by_llm,
        })

        state = doc_state.setdefault(source, {
            "source": source,
            "ranks": [],
            "distances": [],
            "words": set(),
            "used_by_llm": False,
            "version": chunk.get("version", "1.0"),
            "effective_date": chunk.get("effective_date"),
            "document_type": chunk.get("document_type", "general"),
            "loan_type": chunk.get("loan_type", "general"),
        })
        state["ranks"].append(rank)
        state["distances"].append(chunk_node["distance"])
        state["words"] |= chunk_words
        state["used_by_llm"] = state["used_by_llm"] or used_by_llm

    nodes.extend(chunk_nodes)

    # ── Document nodes ─────────────────────────────────────────────────────
    conflict = conflict or {}
    version_resolution = version_resolution or {}
    conflicts = conflict.get("conflicts") or []

    conflicting_sources = {
        claim.get("source")
        for item in conflicts
        for claim in item.get("claims", [])
    }
    authoritative = version_resolution.get("authoritative_source")
    resolution_performed = bool(version_resolution.get("resolution_performed"))

    # resolve_version() sweeps every *undated* document into superseded_sources,
    # because a document with no effective_date cannot out-date one that has
    # them.  That is the right call for picking a single authoritative source,
    # but drawn literally it claims loan_risks.txt is superseded by a fee
    # schedule, which is not a thing anyone means.  A supersedes relation only
    # carries information where there is a disagreement to resolve, so the
    # graph shows it only between documents that actually conflict, and reports
    # the rest as a suppressed count rather than silently dropping them.
    superseded_all = set(version_resolution.get("superseded_sources") or [])
    superseded = superseded_all & conflicting_sources

    document_nodes: list[dict] = []
    for state in sorted(doc_state.values(), key=lambda s: min(s["ranks"])):
        source = state["source"]
        document_nodes.append({
            "id": _document_node_id(source),
            "type": NODE_DOCUMENT,
            "label": source,
            "source": source,
            "chunk_count": len(state["ranks"]),
            "ranks": state["ranks"],
            "best_rank": min(state["ranks"]),
            "best_distance": min(state["distances"]),
            "used_by_llm": state["used_by_llm"],
            "answer_overlap": _overlap_fraction(answer_words, state["words"]),
            "version": state["version"],
            "effective_date": state["effective_date"],
            "document_type": state["document_type"],
            "loan_type": state["loan_type"],
            "in_conflict": source in conflicting_sources,
            "authoritative": resolution_performed and source == authoritative,
            # Superseded on a field this query actually surfaced a
            # disagreement about — see the note above.
            "superseded": source in superseded,
            # Ranked below the authoritative source only for want of a date.
            # Worth surfacing as missing metadata, not as a contradiction.
            "undated": state["effective_date"] is None,
        })
    nodes.extend(document_nodes)

    known_documents = {node["id"] for node in document_nodes}

    # ── Conflict edges ─────────────────────────────────────────────────────
    # One edge per unordered pair of sources that disagree on a field. A pair
    # can disagree on more than one field, so the edge carries a topic list.
    conflict_pairs: dict[tuple, dict] = {}
    for item in conflicts:
        claims = item.get("claims", [])
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                a, b = claims[i], claims[j]
                src_a, src_b = a.get("source"), b.get("source")
                if not src_a or not src_b or src_a == src_b:
                    continue
                id_a, id_b = _document_node_id(src_a), _document_node_id(src_b)
                if id_a not in known_documents or id_b not in known_documents:
                    continue
                key = tuple(sorted((id_a, id_b)))
                entry = conflict_pairs.setdefault(key, {
                    "id": f"e:conflict:{key[0]}|{key[1]}",
                    "source": key[0],
                    "target": key[1],
                    "type": EDGE_CONFLICT,
                    "topics": [],
                    "claims": [],
                })
                topic = item.get("topic", item.get("field_key", "value"))
                if topic not in entry["topics"]:
                    entry["topics"].append(topic)
                for claim in (a, b):
                    record = {
                        "source": claim.get("source"),
                        "value": claim.get("value"),
                        "topic": topic,
                        "field_key": item.get("field_key", ""),
                        "version": claim.get("version"),
                        "effective_date": claim.get("effective_date"),
                    }
                    if record not in entry["claims"]:
                        entry["claims"].append(record)
    edges.extend(conflict_pairs.values())

    # ── Supersedes edges ───────────────────────────────────────────────────
    if resolution_performed and authoritative:
        auth_id = _document_node_id(authoritative)
        if auth_id in known_documents:
            for stale in superseded:
                stale_id = _document_node_id(stale)
                if stale_id not in known_documents:
                    continue
                edges.append({
                    "id": f"e:supersedes:{auth_id}|{stale_id}",
                    "source": auth_id,
                    "target": stale_id,
                    "type": EDGE_SUPERSEDES,
                    "reason": version_resolution.get("reason"),
                    "reason_label": version_resolution.get(
                        "reason_label", version_resolution.get("reason")
                    ),
                })

    # ── Stats ──────────────────────────────────────────────────────────────
    used_nodes = [c for c in chunk_nodes if c["used_by_llm"]]
    stats = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "chunks": len(chunk_nodes),
        "chunks_used_by_llm": len(used_nodes),
        "documents": len(document_nodes),
        "documents_used_by_llm": sum(1 for d in document_nodes if d["used_by_llm"]),
        "conflict_edges": len(conflict_pairs),
        "supersedes_edges": sum(1 for e in edges if e["type"] == EDGE_SUPERSEDES),
        # Documents version resolution ranked below the authoritative source
        # but that the graph does not draw an arc to, because they never
        # disagreed with it — almost always just missing an effective_date.
        "supersedes_suppressed": len(superseded_all - superseded),
        "best_distance": min((c["distance"] for c in chunk_nodes), default=None),
        "worst_distance": max((c["distance"] for c in chunk_nodes), default=None),
        "answer_words": len(answer_words),
        # Overlap of the answer against everything the LLM actually saw. This
        # should track the grounding score closely; a large gap means the
        # answer leaned on chunks that were retrieved but never sent.
        "llm_context_overlap": _overlap_fraction(answer_words, llm_context_words),
    }

    return {"nodes": nodes, "edges": edges, "stats": stats}
