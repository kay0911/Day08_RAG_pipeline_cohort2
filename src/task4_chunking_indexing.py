"""
Task 4 — Chunking & Indexing vào ChromaDB.

Design choices:
- Chunking: RecursiveCharacterTextSplitter, chunk_size=500, overlap=100
  Lý do: 500 chars đủ ngữ cảnh cho 1 đoạn pháp luật; overlap 100 đảm bảo
  câu không bị cắt giữa; recursive separators tôn trọng cấu trúc văn bản.

- Embedding: BAAI/bge-m3 (1024 dim, multilingual)
  Lý do: Được huấn luyện đặc biệt cho tiếng Việt và Đông Nam Á; hỗ trợ
  cả dense và sparse retrieval; SOTA trên MTEB benchmark.

- Vector store: ChromaDB (persistent local)
  Lý do: Không cần Docker, setup đơn giản, hỗ trợ cosine similarity,
  dễ dàng query với custom embeddings.
"""

import logging
import os
import uuid
from pathlib import Path

# Prevent transformers from importing TensorFlow (Keras 3 incompatibility).
# Must be set before any transformers/sentence_transformers import.
os.environ.setdefault("USE_TF", "0")

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma"

# =============================================================================
# CONFIGURATION
# =============================================================================

# chunk_size=500: đủ để chứa 1-2 điều khoản pháp luật, không quá dài gây noise
CHUNK_SIZE = 500
# chunk_overlap=100: 20% overlap để preserve ngữ cảnh qua ranh giới chunk
CHUNK_OVERLAP = 100
CHUNKING_METHOD = "recursive"

# BAAI/bge-m3: multilingual embedding, tốt cho tiếng Việt, 1024 dimensions
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

COLLECTION_NAME = "drug_law_docs"

# =============================================================================
# MODULE-LEVEL SINGLETONS (lazy-initialized)
# =============================================================================

_embedding_model = None
_chroma_client = None
_collection = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        log.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
        import chromadb

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


# =============================================================================
# PIPELINE STEPS
# =============================================================================

def load_documents() -> list[dict]:
    """
    Đọc toàn bộ markdown files từ data/standardized/.

    Returns:
        List of {'content': str, 'metadata': {'source': str, 'type': str}}
    """
    documents = []
    if not STANDARDIZED_DIR.exists():
        log.warning(f"Standardized dir not found: {STANDARDIZED_DIR}")
        return documents

    for md_file in STANDARDIZED_DIR.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if len(content) < 50:
            continue
        doc_type = "legal" if "legal" in str(md_file) else "news"
        documents.append({
            "content": content,
            "metadata": {
                "source": md_file.name,
                "type": doc_type,
                "filepath": str(md_file),
            }
        })

    log.info(f"Loaded {len(documents)} documents from {STANDARDIZED_DIR}")
    return documents


def chunk_documents(documents: list[dict]) -> list[dict]:
    """
    Chunk documents bằng RecursiveCharacterTextSplitter.

    Returns:
        List of {'content': str, 'metadata': dict} — mỗi item là 1 chunk.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # Separators theo thứ tự ưu tiên: double newline → newline → period → space
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    chunks = []
    for doc in documents:
        splits = splitter.split_text(doc["content"])
        for i, chunk_text in enumerate(splits):
            chunk_text = chunk_text.strip()
            if len(chunk_text) < 20:
                continue
            chunks.append({
                "content": chunk_text,
                "metadata": {
                    **doc["metadata"],
                    "chunk_index": i,
                }
            })

    log.info(f"Created {len(chunks)} chunks (avg {sum(len(c['content']) for c in chunks)//max(len(chunks),1)} chars)")
    return chunks


def embed_and_index(chunks: list[dict]) -> None:
    """
    Embed chunks và index vào ChromaDB.
    Bỏ qua chunks đã tồn tại (idempotent).
    """
    model = _get_embedding_model()
    collection = _get_collection()

    # Check existing
    existing_count = collection.count()
    if existing_count > 0:
        log.info(f"Collection already has {existing_count} documents. Clearing and re-indexing...")
        collection.delete(where={"source": {"$ne": ""}})

    texts = [c["content"] for c in chunks]
    log.info(f"Embedding {len(texts)} chunks with {EMBEDDING_MODEL}...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)

    # Batch insert into ChromaDB
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_embeddings = embeddings[i:i + batch_size]

        collection.add(
            ids=[str(uuid.uuid4()) for _ in batch_chunks],
            embeddings=[e.tolist() for e in batch_embeddings],
            documents=[c["content"] for c in batch_chunks],
            metadatas=[c["metadata"] for c in batch_chunks],
        )

    log.info(f"✓ Indexed {collection.count()} chunks into ChromaDB at {CHROMA_DIR}")


def run_pipeline() -> None:
    """Chạy toàn bộ pipeline: load → chunk → embed → index."""
    log.info("=" * 60)
    log.info("Task 4: Chunking & Indexing")
    log.info(f"  Chunking: {CHUNKING_METHOD} (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    log.info(f"  Embedding: {EMBEDDING_MODEL} (dim={EMBEDDING_DIM})")
    log.info(f"  Vector Store: ChromaDB @ {CHROMA_DIR}")
    log.info("=" * 60)

    docs = load_documents()
    if not docs:
        log.error("No documents found. Run task1, task2, task3 first.")
        return

    chunks = chunk_documents(docs)
    if not chunks:
        log.error("No chunks created.")
        return

    embed_and_index(chunks)
    log.info("\n✓ Pipeline complete!")


if __name__ == "__main__":
    run_pipeline()
