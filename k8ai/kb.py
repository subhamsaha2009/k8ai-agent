"""
K8AI Knowledge Base — SQLite FTS5 + RAG vector search.

Three categories:
  - docs       → Azure/K8s official documentation (from docs sync)
  - incidents  → Past incidents saved by the agent
  - runbooks   → User's team runbooks and rules

Search modes:
  - Keyword: SQLite FTS5 with BM25 ranking (always available, offline)
  - Semantic: RAG with embeddings + cosine similarity (requires OpenAI/Azure provider)
  - Hybrid: Combines both for best results (default when embeddings available)

Optional: Azure AI Search backend for team sharing.
"""

import os
import sqlite3
import json
import struct
from datetime import datetime

from k8ai.config import CONFIG_DIR

DB_PATH = os.path.join(CONFIG_DIR, "kb.db")

# ─── Azure AI Search config (optional) ────────────────────────────────────
AZURE_SEARCH_CONFIG = os.path.join(CONFIG_DIR, "azure_search.yaml")


def _get_db():
    """Get SQLite connection with FTS5 tables created."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Main content table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT,
            section TEXT,
            content TEXT NOT NULL,
            url TEXT,
            tags TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # FTS5 virtual table for full-text search
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            title, section, content, tags,
            content=chunks,
            content_rowid=id
        )
    """)

    # Embeddings table for RAG vector search
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id INTEGER PRIMARY KEY,
            vector BLOB NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
        )
    """)

    # Triggers to keep FTS in sync
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, title, section, content, tags)
            VALUES (new.id, new.title, new.section, new.content, new.tags);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, title, section, content, tags)
            VALUES ('delete', old.id, old.title, old.section, old.content, old.tags);
        END
    """)

    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════════════════════════
#  INSERT
# ═══════════════════════════════════════════════════════════════════════════

def add_chunk(source: str, category: str, title: str, section: str,
              content: str, url: str = None, tags: str = None):
    """Add a single chunk to the knowledge base."""
    conn = _get_db()
    conn.execute(
        "INSERT INTO chunks (source, category, title, section, content, url, tags) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source, category, title, section, content, url, tags)
    )
    conn.commit()
    conn.close()


def add_chunks_bulk(chunks: list[dict]):
    """Add multiple chunks efficiently (used by docs sync)."""
    conn = _get_db()
    conn.executemany(
        "INSERT INTO chunks (source, category, title, section, content, url, tags) "
        "VALUES (:source, :category, :title, :section, :content, :url, :tags)",
        chunks
    )
    conn.commit()
    conn.close()


def add_incident(title: str, description: str, resolution: str, tags: str = None):
    """Save a resolved incident to the knowledge base."""
    add_chunk(
        source="agent",
        category="incident",
        title=title,
        section="",
        content=f"{description}\n\nResolution: {resolution}",
        tags=tags,
    )


def add_runbook(title: str, content: str, tags: str = None):
    """Save a team runbook or rule."""
    add_chunk(
        source="user",
        category="runbook",
        title=title,
        section="",
        content=content,
        tags=tags,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  SEARCH
# ═══════════════════════════════════════════════════════════════════════════

def search(query: str, category: str = None, limit: int = 5) -> list[dict]:
    """Search the knowledge base using FTS5 BM25 ranking.
    category: 'docs', 'incident', 'runbook', or None for all."""
    conn = _get_db()

    # Clean query for FTS5 — remove special chars, make each word a prefix match
    words = query.strip().split()
    fts_query = " OR ".join(f'"{w}"' for w in words if len(w) > 1)

    if not fts_query:
        conn.close()
        return []

    try:
        if category:
            rows = conn.execute("""
                SELECT c.*, rank
                FROM chunks_fts fts
                JOIN chunks c ON c.id = fts.rowid
                WHERE chunks_fts MATCH ? AND c.category = ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, category, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT c.*, rank
                FROM chunks_fts fts
                JOIN chunks c ON c.id = fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit)).fetchall()
    except Exception:
        conn.close()
        return []

    results = []
    for row in rows:
        results.append({
            "title": row["title"],
            "section": row["section"],
            "content": row["content"][:1000],
            "source": row["source"],
            "category": row["category"],
            "url": row["url"],
            "tags": row["tags"],
        })

    conn.close()
    return results


def search_docs(query: str, limit: int = 5) -> list[dict]:
    """Search only official docs (Azure + K8s)."""
    return search(query, category="docs", limit=limit)


def search_incidents(query: str, limit: int = 5) -> list[dict]:
    """Search only past incidents."""
    return search(query, category="incident", limit=limit)


def search_knowledge_base(query: str, limit: int = 5) -> list[dict]:
    """Search user's data — incidents + runbooks."""
    incidents = search(query, category="incident", limit=limit)
    runbooks = search(query, category="runbook", limit=limit)
    return incidents + runbooks


# ═══════════════════════════════════════════════════════════════════════════
#  RAG — Vector Embeddings Storage & Semantic Search
# ═══════════════════════════════════════════════════════════════════════════

def _pack_vector(vector: list[float]) -> bytes:
    """Pack a float list into a compact binary blob."""
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack_vector(blob: bytes) -> list[float]:
    """Unpack a binary blob back into a float list."""
    n = len(blob) // 4  # 4 bytes per float
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def store_embeddings(chunk_ids: list[int], vectors: list[list[float]]):
    """Store embedding vectors for chunks."""
    conn = _get_db()
    data = [(cid, _pack_vector(vec)) for cid, vec in zip(chunk_ids, vectors) if vec]
    conn.executemany(
        "INSERT OR REPLACE INTO embeddings (chunk_id, vector) VALUES (?, ?)",
        data
    )
    conn.commit()
    conn.close()


def has_embeddings() -> bool:
    """Check if any embeddings exist in the database."""
    if not os.path.exists(DB_PATH):
        return False
    conn = _get_db()
    count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    conn.close()
    return count > 0


def semantic_search(query_vector: list[float], category: str = None,
                    limit: int = 5) -> list[dict]:
    """Search by cosine similarity against stored embeddings."""
    conn = _get_db()

    if category:
        rows = conn.execute("""
            SELECT c.*, e.vector
            FROM embeddings e
            JOIN chunks c ON c.id = e.chunk_id
            WHERE c.category = ?
        """, (category,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT c.*, e.vector
            FROM embeddings e
            JOIN chunks c ON c.id = e.chunk_id
        """).fetchall()

    conn.close()

    if not rows:
        return []

    # Compute similarities
    scored = []
    for row in rows:
        vec = _unpack_vector(row["vector"])
        sim = _cosine_similarity(query_vector, vec)
        scored.append((sim, row))

    # Sort by similarity (highest first)
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for sim, row in scored[:limit]:
        results.append({
            "title": row["title"],
            "section": row["section"],
            "content": row["content"][:1000],
            "source": row["source"],
            "category": row["category"],
            "url": row["url"],
            "tags": row["tags"],
            "similarity": round(sim, 4),
        })

    return results


def hybrid_search(query: str, query_vector: list[float] = None,
                  category: str = None, limit: int = 5) -> list[dict]:
    """Combine keyword search (FTS5) and semantic search (RAG).
    If embeddings are available, merges both result sets with deduplication.
    Falls back to keyword-only if no embeddings."""

    # Keyword results (always available)
    keyword_results = search(query, category=category, limit=limit)

    # Semantic results (only if vector provided and embeddings exist)
    if query_vector and has_embeddings():
        semantic_results = semantic_search(query_vector, category=category, limit=limit)
    else:
        return keyword_results

    # Merge and deduplicate by title+section
    seen = set()
    merged = []

    # Semantic results first (they capture meaning better)
    for r in semantic_results:
        key = (r["title"], r["section"])
        if key not in seen:
            seen.add(key)
            r["match_type"] = "semantic"
            merged.append(r)

    # Then keyword results
    for r in keyword_results:
        key = (r["title"], r["section"])
        if key not in seen:
            seen.add(key)
            r["match_type"] = "keyword"
            merged.append(r)

    return merged[:limit]


# ═══════════════════════════════════════════════════════════════════════════
#  MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def clear_category(category: str):
    """Delete all chunks in a category (used before re-syncing docs)."""
    conn = _get_db()
    conn.execute("DELETE FROM chunks WHERE category = ?", (category,))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Get counts by category."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT category, COUNT(*) as count FROM chunks GROUP BY category"
    ).fetchall()
    conn.close()

    stats = {row["category"]: row["count"] for row in rows}
    stats["total"] = sum(stats.values())
    stats["db_path"] = DB_PATH

    # Embedding stats
    conn2 = _get_db()
    emb_count = conn2.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    conn2.close()
    stats["embeddings"] = emb_count
    stats["rag_enabled"] = emb_count > 0

    if os.path.exists(DB_PATH):
        stats["db_size_mb"] = round(os.path.getsize(DB_PATH) / (1024 * 1024), 1)
    return stats


def is_docs_synced() -> bool:
    """Check if docs have been synced at least once."""
    if not os.path.exists(DB_PATH):
        return False
    conn = _get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE category = 'docs'"
    ).fetchone()[0]
    conn.close()
    return count > 0


# ═══════════════════════════════════════════════════════════════════════════
#  AZURE AI SEARCH (optional backend)
# ═══════════════════════════════════════════════════════════════════════════

def setup_azure_search(endpoint: str, api_key: str, index_name: str = "k8ai-kb"):
    """Save Azure AI Search config for team sharing."""
    import yaml
    os.makedirs(CONFIG_DIR, exist_ok=True)
    config = {
        "endpoint": endpoint,
        "api_key": api_key,
        "index_name": index_name,
    }
    with open(AZURE_SEARCH_CONFIG, "w") as f:
        yaml.dump(config, f)
    return True


def is_azure_search_configured() -> bool:
    """Check if Azure AI Search is set up."""
    return os.path.exists(AZURE_SEARCH_CONFIG)


def search_azure(query: str, limit: int = 5) -> list[dict]:
    """Search Azure AI Search index (if configured)."""
    import yaml
    import urllib.request

    if not is_azure_search_configured():
        return []

    with open(AZURE_SEARCH_CONFIG) as f:
        config = yaml.safe_load(f)

    endpoint = config["endpoint"].rstrip("/")
    api_key = config["api_key"]
    index_name = config["index_name"]

    url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"
    body = json.dumps({
        "search": query,
        "top": limit,
        "queryType": "simple",
    }).encode()

    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "api-key": api_key,
    })

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = []
        for r in data.get("value", []):
            results.append({
                "title": r.get("title", ""),
                "content": r.get("content", "")[:1000],
                "source": r.get("source", "azure-search"),
                "category": r.get("category", ""),
                "tags": r.get("tags", ""),
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]
