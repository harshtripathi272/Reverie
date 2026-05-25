"""RAG question-answering agent with realistic memory operations.

This is the shape of every "chat with your docs" agent shipping today:
embed user query → retrieve top-k from a vector store → pass results
to the LLM → answer.

Why Reverie matters here
------------------------

The #1 failure mode of RAG agents in production is **poison memory** —
the retrieval step returns irrelevant or wrong results, and the LLM
confidently produces a wrong answer based on them. Reverie's anomaly
detector flags this automatically when retrieval scores are low or
when the LLM ignores the retrieved chunks.

In this example we deliberately seed a few "wrong" docs to demonstrate
how the visualization makes the failure obvious.

Setup
-----

    export NVIDIA_API_KEY=<your key>
    pip install openai httpx
    python rag_qa_agent.py "What is observability for AI agents?"

Replace the in-memory ``KNOWLEDGE_BASE`` and ``embed_and_search`` with a
real vector store (Chroma, Qdrant, Weaviate, pgvector) when integrating.
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Make ``reverie_emit`` importable when running from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reverie_emit import ReverieClient  # noqa: E402

from openai import OpenAI  # noqa: E402

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "bytedance/seed-oss-36b-instruct"


@dataclass
class Doc:
    id: str
    title: str
    text: str


# Stand-in for a real vector store. Each doc represents an embedded chunk.
KNOWLEDGE_BASE: list[Doc] = [
    Doc(
        id="d-001",
        title="Reverie introduction",
        text=(
            "Reverie is a cognitive observability platform for autonomous AI "
            "agents. It captures every cognitive event (goals, tool calls, "
            "memory retrievals, retries, sub-agent spawns) and renders the "
            "entire run as a 3D world of glowing orbs."
        ),
    ),
    Doc(
        id="d-002",
        title="OpenTelemetry primer",
        text=(
            "OpenTelemetry is an open-source observability framework that "
            "standardises traces, metrics, and logs for distributed systems. "
            "It defines a common vocabulary so vendors don't have to."
        ),
    ),
    Doc(
        id="d-003",
        title="Why agent debugging is hard",
        text=(
            "Agents are non-deterministic. The same prompt produces different "
            "trajectories. Traditional logs show the events but not the "
            "causal structure between them, making debugging extremely time "
            "consuming."
        ),
    ),
    # Deliberately off-topic — demonstrates poison-memory behaviour when
    # the retriever surfaces low-relevance results.
    Doc(
        id="d-099",
        title="(off-topic) Tomato soup recipe",
        text="Combine tomatoes, basil, cream, and salt. Simmer 20 minutes.",
    ),
    Doc(
        id="d-100",
        title="(off-topic) Bicycle maintenance",
        text="Check tyre pressure weekly. Lubricate the chain every 200km.",
    ),
]


def embed_and_search(query: str, k: int = 3) -> list[tuple[Doc, float]]:
    """Pretend vector search.

    Real implementations call into an embedder + ANN index. We approximate
    relevance with a token-overlap score so the returned ranking varies
    with the query — including, intentionally, returning poison results
    when the query has no overlap with the on-topic docs.
    """

    q_terms = set(re.findall(r"\w+", query.lower()))
    scored: list[tuple[Doc, float]] = []
    for doc in KNOWLEDGE_BASE:
        terms = set(re.findall(r"\w+", (doc.title + " " + doc.text).lower()))
        overlap = len(q_terms & terms)
        score = overlap / max(len(q_terms), 1)
        scored.append((doc, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


def call_llm(
    client: OpenAI,
    rev: ReverieClient,
    *,
    parent_id: str,
    query: str,
    contexts: list[Doc],
) -> tuple[str, int]:
    """Run the answer generation. Returns (text, total_tokens)."""

    context_block = "\n\n".join(
        f"[{d.id}] {d.title}\n{d.text}" for d in contexts
    )
    prompt = (
        f"You are a helpful assistant. Answer the user question using ONLY "
        f"the context below. If the context is irrelevant, say "
        f"\"I don't have enough information.\"\n\n"
        f"Context:\n{context_block}\n\n"
        f"User question: {query}"
    )

    call_id = rev.tool_called(
        f"{MODEL}.answer",
        input={"query": query, "context_doc_ids": [d.id for d in contexts]},
        parent_id=parent_id,
    )
    started = time.time()
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=500,
    )
    text = completion.choices[0].message.content or ""
    tokens = (
        getattr(completion.usage, "total_tokens", 0)
        if completion.usage
        else len(text.split())
    )
    rev.tool_returned(
        f"{MODEL}.answer",
        output={"text": text, "tokens": tokens},
        latency_ms=(time.time() - started) * 1000,
        token_cost=int(tokens),
        parent_id=call_id,
    )
    return text.strip(), int(tokens)


def run(query: str) -> str:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("error: NVIDIA_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
    rev = ReverieClient(agent_id="rag-qa-bot", runtime="nvidia-nim")
    rev.start_run(goal=f"RAG answer for: {query}")

    goal_id = rev.goal(intent=query)

    # ---- Step 1: retrieval.
    retrieval_started = time.time()
    hits = embed_and_search(query, k=4)
    avg_score = sum(s for _, s in hits) / max(len(hits), 1)

    rev.memory_retrieved(
        query=query,
        results=[
            {"id": d.id, "title": d.title, "score": round(score, 3)}
            for d, score in hits
        ],
        parent_id=goal_id,
    )

    # If everything has zero overlap, that's a poison-memory situation.
    # Reverie's anomaly detector picks this up by salience score later;
    # we also emit an explicit reflection so the user sees it in the panel.
    if avg_score == 0.0:
        rev.reflection(
            insight=(
                "Retrieval returned no relevant documents (avg score 0.0). "
                "The model is about to hallucinate based on off-topic context."
            ),
            parent_id=goal_id,
        )

    # ---- Step 2: answer generation.
    contexts = [d for d, _ in hits]
    try:
        answer, tokens = call_llm(
            client, rev, parent_id=goal_id, query=query, contexts=contexts
        )
    except Exception as exc:
        rev.error(message=str(exc), parent_id=goal_id)
        rev.goal_failed(parent_id=goal_id, reason=str(exc))
        rev.complete_run(status="failed")
        raise

    # ---- Step 3: validation. Cheap heuristic — does the answer reference
    # any of the retrieved doc ids? If not, the model probably ignored the
    # context (or the context was useless). This is the kind of automatic
    # check production RAG systems badly need.
    referenced = [d.id for d in contexts if d.id in answer or d.title.lower() in answer.lower()]
    if not referenced and "I don't have enough information" not in answer:
        rev.error(
            message=(
                "Answer doesn't reference any retrieved documents. "
                "Possible hallucination."
            ),
            parent_id=goal_id,
        )
    else:
        rev.reflection(
            insight=f"Answer references {len(referenced)} of {len(contexts)} retrieved docs",
            parent_id=goal_id,
        )

    rev.goal_completed(parent_id=goal_id, outcome=answer[:80])
    rev.complete_run()
    rev.close()

    print("\n========== ANSWER ==========\n")
    print(answer)
    print("\n============================\n")
    print(f"Retrieved doc ids: {[d.id for d in contexts]}")
    print(f"Average retrieval score: {avg_score:.3f}")
    print(f"\n[reverie] run id: {rev.run_id}")
    print(f"[reverie] view at: http://localhost:3000/run?id={rev.run_id}")
    return answer


if __name__ == "__main__":
    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What is observability for AI agents and why does it matter?"
    )
    run(query)
