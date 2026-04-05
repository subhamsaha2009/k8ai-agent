"""
K8AI Embeddings — Generate text embeddings using the configured AI provider.

Supports:
  - Azure OpenAI (text-embedding-ada-002 / text-embedding-3-small)
  - OpenAI (same models)
  - Claude: no embedding model — falls back to keyword search

Embeddings are used for RAG (semantic search) in the knowledge base.
"""

import os

# Embedding model to use (same for Azure and OpenAI)
EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_DIMENSIONS = 1536
BATCH_SIZE = 100  # max texts per API call


def _get_client():
    """Get the OpenAI/Azure client for embeddings."""
    provider = os.getenv("AI_PROVIDER", "").lower()

    if provider == "azure":
        from openai import AzureOpenAI
        return AzureOpenAI(
            api_key=os.getenv("AI_API_KEY"),
            azure_endpoint=os.getenv("AI_ENDPOINT"),
            api_version=os.getenv("AI_API_VERSION", "2024-10-21"),
        ), "azure"

    elif provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=os.getenv("AI_API_KEY")), "openai"

    elif provider == "claude":
        return None, "claude"

    return None, "unknown"


def is_embedding_available() -> bool:
    """Check if the current provider supports embeddings."""
    provider = os.getenv("AI_PROVIDER", "").lower()
    return provider in ("azure", "openai")


def get_embedding(text: str) -> list[float] | None:
    """Generate embedding for a single text. Returns None if not available."""
    client, provider = _get_client()
    if client is None:
        return None

    try:
        text = text.replace("\n", " ").strip()
        if not text:
            return None

        response = client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL,
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"  [embedding error] {e}")
        return None


def get_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """Generate embeddings for multiple texts in batches.
    Returns list of embeddings (same order as input). None for failures."""
    client, provider = _get_client()
    if client is None:
        return [None] * len(texts)

    results = [None] * len(texts)

    # Process in batches
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]

        # Clean texts
        cleaned = [t.replace("\n", " ").strip() for t in batch]
        # Skip empty texts
        cleaned = [t if t else "empty" for t in cleaned]

        try:
            response = client.embeddings.create(
                input=cleaned,
                model=EMBEDDING_MODEL,
            )
            for j, item in enumerate(response.data):
                results[i + j] = item.embedding
        except Exception as e:
            print(f"  [embedding batch error at {i}] {e}")
            # Leave as None for this batch

    return results
