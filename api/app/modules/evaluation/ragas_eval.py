"""
RAGAS Evaluation Module
Evaluates LLM response quality using: faithfulness, answer_relevancy, context_precision.
Called optionally from the chat agent to avoid adding latency to every request.
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def evaluate_response(
    question: str,
    answer: str,
    contexts: List[str],
    ground_truth: Optional[str] = None,
) -> dict:
    """
    Evaluate a single RAG response using RAGAS metrics.

    Returns a dict with scores for: faithfulness, answer_relevancy, context_precision.
    Returns an error dict if RAGAS is unavailable or evaluation fails.
    """
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision
        from datasets import Dataset

        data = {
            "question": [question],
            "answer": [answer],
            "contexts": [contexts],
        }
        if ground_truth:
            data["ground_truth"] = [ground_truth]

        dataset = Dataset.from_dict(data)

        metrics = [faithfulness, answer_relevancy]
        if ground_truth:
            metrics.append(context_precision)

        result = evaluate(dataset, metrics=metrics)
        scores = result.to_pandas().to_dict(orient="records")[0]

        return {
            "faithfulness": round(float(scores.get("faithfulness", 0)), 4),
            "answer_relevancy": round(float(scores.get("answer_relevancy", 0)), 4),
            "context_precision": round(float(scores.get("context_precision", 0)), 4) if ground_truth else None,
        }

    except ImportError:
        logger.warning("RAGAS not installed — skipping evaluation")
        return {"error": "ragas not installed"}
    except Exception as e:
        logger.error("RAGAS evaluation error: %s", e)
        return {"error": str(e)}


def batch_evaluate(qa_pairs: List[dict]) -> List[dict]:
    """
    Evaluate multiple QA pairs at once.
    Each dict in qa_pairs must have: question, answer, contexts (list of str).
    Optional: ground_truth.
    """
    return [
        evaluate_response(
            question=pair["question"],
            answer=pair["answer"],
            contexts=pair["contexts"],
            ground_truth=pair.get("ground_truth"),
        )
        for pair in qa_pairs
    ]
