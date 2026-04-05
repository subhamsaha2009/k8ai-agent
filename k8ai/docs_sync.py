"""
Docs Sync — Download Azure AKS + Kubernetes docs from GitHub, chunk, and store locally.

Sources:
  - AKS docs: github.com/MicrosoftDocs/azure-aks-docs (articles/aks/*.md)
  - K8s docs: github.com/kubernetes/website (content/en/docs/concepts + tasks)

Chunks are stored in SQLite FTS5 via kb.py for instant offline search.
"""

import os
import re
import io
import zipfile
import urllib.request
from datetime import datetime

from k8ai.kb import add_chunks_bulk, clear_category, get_stats, store_embeddings
from k8ai.config import CONFIG_DIR
from k8ai.embeddings import is_embedding_available, get_embeddings_batch

SYNC_STATUS_FILE = os.path.join(CONFIG_DIR, "docs_sync.json")

# ─── GitHub ZIP URLs ──────────────────────────────────────────────────────
AKS_DOCS_ZIP = "https://github.com/MicrosoftDocs/azure-aks-docs/archive/refs/heads/main.zip"
K8S_DOCS_ZIP = "https://github.com/kubernetes/website/archive/refs/heads/main.zip"

# Only download these folders from K8s (full repo is too big)
K8S_INCLUDE_PATHS = [
    "content/en/docs/concepts/",
    "content/en/docs/tasks/",
]


def _download_zip(url: str, progress_callback=None) -> zipfile.ZipFile:
    """Download a ZIP file from URL and return as ZipFile object."""
    req = urllib.request.Request(url, headers={"User-Agent": "k8ai-agent/1.0"})
    resp = urllib.request.urlopen(req, timeout=120)
    data = resp.read()
    if progress_callback:
        progress_callback(len(data))
    return zipfile.ZipFile(io.BytesIO(data))


def _extract_md_files(zf: zipfile.ZipFile, prefix: str,
                      include_paths: list = None) -> list[tuple[str, str]]:
    """Extract .md files from ZIP. Returns list of (filename, content)."""
    files = []
    for info in zf.infolist():
        if not info.filename.endswith(".md"):
            continue
        if info.is_dir():
            continue

        # Get path relative to the repo root (strip the top-level folder)
        parts = info.filename.split("/", 1)
        if len(parts) < 2:
            continue
        rel_path = parts[1]

        # Filter by include paths if specified
        if include_paths:
            if not any(rel_path.startswith(p) for p in include_paths):
                continue

        try:
            content = zf.read(info.filename).decode("utf-8", errors="replace")
            if len(content.strip()) < 100:
                continue  # skip tiny files
            files.append((rel_path, content))
        except Exception:
            continue

    return files


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content


def _chunk_markdown(content: str, title: str, max_words: int = 400) -> list[dict]:
    """Split markdown content into chunks by headings.
    Each chunk keeps its section heading for context."""
    content = _strip_frontmatter(content)

    # Remove reference links at bottom
    content = re.sub(r'\n\[[\w-]+\]:.*', '', content)
    content = content.strip()

    if not content:
        return []

    # Split by headings (## or ###)
    sections = re.split(r'\n(?=#{1,3}\s)', content)
    chunks = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract section heading
        heading_match = re.match(r'^(#{1,3})\s+(.+)', section)
        section_title = heading_match.group(2).strip() if heading_match else ""

        # If section is too long, split by paragraphs
        words = section.split()
        if len(words) <= max_words:
            if len(words) > 20:  # skip very small chunks
                chunks.append({
                    "title": title,
                    "section": section_title,
                    "content": section,
                })
        else:
            # Split long sections into ~max_words chunks
            paragraphs = section.split("\n\n")
            current = []
            current_words = 0

            for para in paragraphs:
                para_words = len(para.split())
                if current_words + para_words > max_words and current:
                    text = "\n\n".join(current)
                    if len(text.split()) > 20:
                        chunks.append({
                            "title": title,
                            "section": section_title,
                            "content": text,
                        })
                    current = [para]
                    current_words = para_words
                else:
                    current.append(para)
                    current_words += para_words

            if current:
                text = "\n\n".join(current)
                if len(text.split()) > 20:
                    chunks.append({
                        "title": title,
                        "section": section_title,
                        "content": text,
                    })

    return chunks


def sync_aks_docs(progress_callback=None) -> int:
    """Download and index AKS docs. Returns chunk count."""
    if progress_callback:
        progress_callback("Downloading AKS docs from GitHub...")

    zf = _download_zip(AKS_DOCS_ZIP)
    md_files = _extract_md_files(zf, "articles/aks/")

    # Filter to only articles/aks/ folder
    aks_files = [(f, c) for f, c in md_files if f.startswith("articles/aks/")]

    if progress_callback:
        progress_callback(f"  Found {len(aks_files)} AKS doc files")

    all_chunks = []
    for filepath, content in aks_files:
        # Extract title from filename
        filename = os.path.basename(filepath).replace(".md", "").replace("-", " ").title()
        url = f"https://learn.microsoft.com/en-us/azure/aks/{os.path.basename(filepath).replace('.md', '')}"

        chunks = _chunk_markdown(content, filename)
        for chunk in chunks:
            chunk["source"] = filepath
            chunk["category"] = "docs"
            chunk["url"] = url
            chunk["tags"] = "azure aks " + filename.lower()
        all_chunks.extend(chunks)

    if all_chunks:
        add_chunks_bulk(all_chunks)

    if progress_callback:
        progress_callback(f"  Indexed {len(all_chunks)} chunks from AKS docs")

    return len(all_chunks)


def sync_k8s_docs(progress_callback=None) -> int:
    """Download and index Kubernetes docs. Returns chunk count."""
    if progress_callback:
        progress_callback("Downloading Kubernetes docs from GitHub...")
        progress_callback("  (this is a large download, may take a minute)")

    zf = _download_zip(K8S_DOCS_ZIP)
    md_files = _extract_md_files(zf, "content/en/docs/", K8S_INCLUDE_PATHS)

    if progress_callback:
        progress_callback(f"  Found {len(md_files)} K8s doc files")

    all_chunks = []
    for filepath, content in md_files:
        filename = os.path.basename(filepath).replace(".md", "").replace("_", " ").replace("-", " ").title()
        # Build kubernetes.io URL from filepath
        url_path = filepath.replace("content/en/", "").replace(".md", "").replace("_index", "")
        url = f"https://kubernetes.io/{url_path}"

        chunks = _chunk_markdown(content, filename)
        for chunk in chunks:
            chunk["source"] = filepath
            chunk["category"] = "docs"
            chunk["url"] = url
            chunk["tags"] = "kubernetes k8s " + filename.lower()
        all_chunks.extend(chunks)

    if all_chunks:
        add_chunks_bulk(all_chunks)

    if progress_callback:
        progress_callback(f"  Indexed {len(all_chunks)} chunks from K8s docs")

    return len(all_chunks)


def _generate_embeddings(progress_callback=None):
    """Generate embeddings for all doc chunks that don't have one yet."""
    import sqlite3

    if not is_embedding_available():
        if progress_callback:
            progress_callback("Skipping embeddings (Claude provider — no embedding model)")
        return 0

    if progress_callback:
        progress_callback("Generating RAG embeddings...")

    db_path = os.path.join(CONFIG_DIR, "kb.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get chunks without embeddings
    rows = conn.execute("""
        SELECT c.id, c.title, c.section, c.content
        FROM chunks c
        LEFT JOIN embeddings e ON e.chunk_id = c.id
        WHERE e.chunk_id IS NULL AND c.category = 'docs'
    """).fetchall()
    conn.close()

    if not rows:
        if progress_callback:
            progress_callback("  All chunks already have embeddings")
        return 0

    total = len(rows)
    if progress_callback:
        progress_callback(f"  {total} chunks need embeddings")

    # Process in batches
    batch_size = 100
    generated = 0

    for i in range(0, total, batch_size):
        batch_rows = rows[i:i + batch_size]

        # Build text for each chunk: title + section + content (truncated)
        texts = []
        chunk_ids = []
        for row in batch_rows:
            text = f"{row['title']} - {row['section']}\n{row['content'][:500]}"
            texts.append(text)
            chunk_ids.append(row["id"])

        vectors = get_embeddings_batch(texts)

        # Store valid embeddings
        valid_ids = []
        valid_vecs = []
        for cid, vec in zip(chunk_ids, vectors):
            if vec is not None:
                valid_ids.append(cid)
                valid_vecs.append(vec)

        if valid_ids:
            store_embeddings(valid_ids, valid_vecs)
            generated += len(valid_ids)

        if progress_callback:
            progress_callback(f"  Embedded {min(i + batch_size, total)}/{total} chunks")

    if progress_callback:
        progress_callback(f"  RAG ready — {generated} embeddings generated")

    return generated


def sync_all(progress_callback=None) -> dict:
    """Full sync — download AKS + K8s docs, chunk, store, generate embeddings."""
    import json

    # Clear existing docs before re-syncing
    clear_category("docs")

    aks_count = sync_aks_docs(progress_callback)
    k8s_count = sync_k8s_docs(progress_callback)

    # Generate RAG embeddings
    emb_count = _generate_embeddings(progress_callback)

    # Save sync status
    os.makedirs(CONFIG_DIR, exist_ok=True)
    status = {
        "last_sync": datetime.now().isoformat(),
        "aks_chunks": aks_count,
        "k8s_chunks": k8s_count,
        "total_chunks": aks_count + k8s_count,
        "embeddings": emb_count,
        "rag_enabled": emb_count > 0,
    }
    with open(SYNC_STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)

    return status


def get_sync_status() -> dict | None:
    """Get last sync info."""
    import json
    if not os.path.exists(SYNC_STATUS_FILE):
        return None
    with open(SYNC_STATUS_FILE) as f:
        return json.load(f)
