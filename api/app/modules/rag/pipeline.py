import logging
from typing import List
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_chroma_client():
    import chromadb
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def get_embeddings():
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(api_key=settings.openai_api_key)


def get_vector_store(collection_name: str):
    from langchain_chroma import Chroma
    return Chroma(
        client=get_chroma_client(),
        collection_name=collection_name,
        embedding_function=get_embeddings(),
    )


def ingest_text(text: str, metadata: dict, collection: str = "family_finance") -> List[str]:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text(text)
    if not chunks:
        return []

    store = get_vector_store(collection)
    ids = store.add_texts(chunks, metadatas=[metadata] * len(chunks))
    logger.info("Ingested %d chunks into collection '%s'", len(chunks), collection)
    return ids
