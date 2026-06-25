"""
RAGAS Evaluation Module
Evaluates LLM response quality using Faithfulness and AnswerRelevancy.
Uses RAGAS 0.2.x API with Azure OpenAI via LangChain wrappers.
Called optionally from the chat endpoint when the client requests evaluation.
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Module-level cache so we only build LLM/embedding wrappers once per process.
_ragas_llm = None
_ragas_embeddings = None


def _get_ragas_llm():
    global _ragas_llm
    if _ragas_llm is None:
        from langchain_openai import AzureChatOpenAI
        from ragas.llms import LangchainLLMWrapper
        from app.core.config import settings

        llm = AzureChatOpenAI(
            azure_deployment=settings.azure_openai_deployment,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            temperature=0,
        )
        _ragas_llm = LangchainLLMWrapper(llm)
    return _ragas_llm


def _get_ragas_embeddings():
    global _ragas_embeddings
    if _ragas_embeddings is None:
        from langchain_openai import AzureOpenAIEmbeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from app.core.config import settings

        embeddings = AzureOpenAIEmbeddings(
            azure_deployment=settings.azure_openai_embedding_deployment,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        _ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)
    return _ragas_embeddings


def evaluate_response(
    question: str,
    answer: str,
    contexts: List[str],
    ground_truth: Optional[str] = None,
) -> dict:
    """
    Evaluate a single RAG response.

    Returns a dict with:
      - faithfulness      : 0-1, how grounded the answer is in the retrieved contexts
      - answer_relevancy  : 0-1, how relevant the answer is to the question
      - context_precision : 0-1, precision of retrieved contexts (only when ground_truth given)
      - error             : present only when evaluation could not run
    """
    if not contexts:
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": None,
            "error": "no_contexts",
        }

    try:
        from ragas import evaluate
        from ragas.metrics import Faithfulness, AnswerRelevancy
        from ragas.dataset_schema import SingleTurnSample, EvaluationDataset

        ragas_llm = _get_ragas_llm()
        ragas_emb = _get_ragas_embeddings()

        sample = SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
            reference=ground_truth,
        )
        dataset = EvaluationDataset(samples=[sample])

        metrics = [
            Faithfulness(llm=ragas_llm),
            AnswerRelevancy(llm=ragas_llm, embeddings=ragas_emb),
        ]

        result = evaluate(dataset=dataset, metrics=metrics)
        row = result.to_pandas().iloc[0].to_dict()

        return {
            "faithfulness": _safe_float(row.get("faithfulness")),
            "answer_relevancy": _safe_float(row.get("answer_relevancy")),
            "context_precision": None,
        }

    except ImportError:
        logger.warning("RAGAS not installed — skipping evaluation")
        return {"error": "ragas_not_installed", "faithfulness": None, "answer_relevancy": None, "context_precision": None}
    except Exception as exc:
        logger.error("RAGAS evaluation error: %s", exc)
        return {"error": str(exc), "faithfulness": None, "answer_relevancy": None, "context_precision": None}


def _safe_float(value) -> Optional[float]:
    try:
        return round(float(value), 4) if value is not None else None
    except (TypeError, ValueError):
        return None


def batch_evaluate(qa_pairs: List[dict]) -> List[dict]:
    """
    Evaluate multiple QA pairs at once.
    Each dict must have: question, answer, contexts (list[str]).
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
