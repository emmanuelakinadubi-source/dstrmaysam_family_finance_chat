"""
Chat Agent — RAG-powered QA agent scoped to uploaded event documents.
Uses LangChain's RetrievalQA chain with ChromaDB as the vector store.
Supports optional RAGAS evaluation of responses.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

EVENT_SYSTEM_PROMPT = """You are an AI assistant that answers questions about company event plans.
You have access to uploaded event documents. Use only the retrieved context to answer.
If the answer is not in the context, say "I could not find this information in the uploaded event documents."
Be concise and specific. Quote relevant numbers when available."""


def get_event_rag_chain(event_id: Optional[str] = None):
    """
    Build a RAG retrieval chain scoped to event documents.
    If event_id is provided, filter to that specific event's documents.
    """
    from langchain_chroma import Chroma
    from langchain.chains import RetrievalQA
    from langchain_core.prompts import PromptTemplate
    from app.modules.rag.pipeline import get_chroma_client, get_embeddings

    client = get_chroma_client()
    embeddings = get_embeddings()

    search_kwargs: dict = {"k": 4}
    if event_id:
        search_kwargs["filter"] = {"event_id": event_id}

    vector_store = Chroma(
        client=client,
        collection_name="event_documents",
        embedding_function=embeddings,
    )
    retriever = vector_store.as_retriever(search_kwargs=search_kwargs)

    from app.modules.chat.llm import get_llm
    llm = get_llm()

    prompt = PromptTemplate(
        input_variables=["context", "question"],
        template=(
            f"{EVENT_SYSTEM_PROMPT}\n\n"
            "Context:\n{context}\n\n"
            "Question: {question}\n"
            "Answer:"
        ),
    )

    chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )
    return chain


def run_event_chat(
    question: str,
    event_id: Optional[str] = None,
    evaluate: bool = False,
) -> dict:
    """
    Run a question through the event RAG chain.
    Optionally evaluate the response with RAGAS.
    """
    import time

    try:
        chain = get_event_rag_chain(event_id)
        start = time.time()
        result = chain.invoke({"query": question})
        latency_ms = round((time.time() - start) * 1000, 1)

        answer = result.get("result", "")
        source_docs = result.get("source_documents", [])
        contexts = [d.page_content for d in source_docs]

        response = {
            "answer": answer,
            "contexts": contexts,
            "latency_ms": latency_ms,
            "ragas_scores": None,
        }

        if evaluate and contexts:
            try:
                from app.modules.evaluation.ragas_eval import evaluate_response
                scores = evaluate_response(question, answer, contexts)
                response["ragas_scores"] = scores
            except Exception as e:
                logger.warning("RAGAS evaluation skipped: %s", e)

        return response

    except Exception as e:
        logger.error("Chat agent error: %s", e)
        return {
            "answer": f"Unable to retrieve answer: {e}",
            "contexts": [],
            "latency_ms": None,
            "ragas_scores": None,
        }
