"""Generation metrics via Ragas (faithfulness / answer_relevancy / context_precision).

Two halves, deliberately split: `build_samples` runs the Q&A pipeline and assembles
the evaluation dataset — pure and unit-testable with a FunctionModel — while
`evaluate_generation` makes the actual Ragas call behind a lazy import. Ragas is a
heavy eval-only dependency and needs a live LLM + embeddings, so this runs in the
nightly/live job, never in keyless PR CI.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel
from pydantic_ai.models import Model

from requirements_audit.config import Settings
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import GoldenQuestion, ScenarioTag
from requirements_audit.orchestrator import answer_query
from requirements_audit.retrieval.lexical import LexicalIndex


class GenerationSample(BaseModel):
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str


class GenerationScore(BaseModel):
    faithfulness: float
    answer_relevancy: float
    context_precision: float


def build_samples(
    store: SqliteStore,
    questions: Sequence[GoldenQuestion],
    settings: Settings,
    *,
    model: Model | None = None,
    k: int = 5,
) -> list[GenerationSample]:
    """Run the Q&A path over answerable golden questions and assemble Ragas samples.

    Contexts are the top-k retrieved requirement texts (what the answer was grounded
    in); ground_truth is the question's expected facts.
    """
    index = LexicalIndex.from_store(store)
    samples: list[GenerationSample] = []
    for q in questions:
        if q.scenario is not ScenarioTag.SUCCESS or not q.expected_facts:
            continue
        answer, _trace = answer_query(store, q.question, settings, model=model)
        contexts = [hit.chunk.text for hit in index.search(q.question, k)]
        samples.append(
            GenerationSample(
                question=q.question,
                answer=answer.text,
                contexts=contexts,
                ground_truth="; ".join(q.expected_facts),
            )
        )
    return samples


def evaluate_generation(samples: Sequence[GenerationSample]) -> GenerationScore:
    """Call Ragas on the assembled samples. Requires the eval extra + a live LLM."""
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import answer_relevancy, context_precision, faithfulness

    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": s.question,
                "response": s.answer,
                "retrieved_contexts": s.contexts,
                "reference": s.ground_truth,
            }
            for s in samples
        ]
    )
    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision])
    scores = result.to_pandas()[["faithfulness", "answer_relevancy", "context_precision"]].mean()
    return GenerationScore(
        faithfulness=float(scores["faithfulness"]),
        answer_relevancy=float(scores["answer_relevancy"]),
        context_precision=float(scores["context_precision"]),
    )
