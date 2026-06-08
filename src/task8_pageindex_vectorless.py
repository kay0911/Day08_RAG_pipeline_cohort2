"""
Task 8 — PageIndex Vectorless RAG.

PageIndex sử dụng structural understanding của document thay vì embedding vectors,
cho phép RAG chính xác hơn trên tài liệu có cấu trúc rõ ràng (như văn bản pháp luật).

Graceful fallback: nếu không có PAGEINDEX_API_KEY, hàm trả về empty list
thay vì raise exception — cho phép pipeline hoạt động mà không cần API key.

Tham khảo: https://github.com/VectifyAI/PageIndex
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"

# Index ID sau khi upload (lưu vào env hoặc config)
PAGEINDEX_INDEX_ID = os.getenv("PAGEINDEX_INDEX_ID", "")


def upload_documents() -> str | None:
    """
    Upload toàn bộ markdown documents lên PageIndex.

    Returns:
        Index ID nếu thành công, None nếu thất bại.
    """
    if not PAGEINDEX_API_KEY:
        log.warning("PAGEINDEX_API_KEY not set. Skipping upload.")
        return None

    try:
        import pageindex

        pi = pageindex.PageIndex(api_key=PAGEINDEX_API_KEY)

        md_files = list(STANDARDIZED_DIR.rglob("*.md"))
        if not md_files:
            log.warning("No markdown files found to upload.")
            return None

        documents = []
        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            documents.append({
                "content": content,
                "metadata": {
                    "filename": md_file.name,
                    "type": "legal" if "legal" in str(md_file) else "news",
                }
            })

        index_id = pi.create_index(documents=documents)
        log.info(f"✓ Uploaded {len(documents)} documents. Index ID: {index_id}")
        return index_id

    except ImportError:
        log.warning("pageindex package not installed. Install with: pip install pageindex")
        return None
    except Exception as e:
        log.error(f"Upload failed: {e}")
        return None


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """
    Vectorless retrieval sử dụng PageIndex.
    Dùng làm fallback khi hybrid search không có kết quả tốt.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,
            'metadata': dict,
            'source': 'pageindex'
        }
        Trả về empty list nếu không có API key (graceful fallback).
    """
    if not PAGEINDEX_API_KEY:
        log.debug("PAGEINDEX_API_KEY not set — pageindex_search returns empty list (fallback mode).")
        return []

    try:
        import pageindex

        pi = pageindex.PageIndex(api_key=PAGEINDEX_API_KEY)

        index_id = PAGEINDEX_INDEX_ID or _get_or_create_index(pi)
        if not index_id:
            return []

        results = pi.query(index_id=index_id, query=query, top_k=top_k)

        return [
            {
                "content": r.text if hasattr(r, "text") else str(r),
                "score": float(r.score) if hasattr(r, "score") else 0.5,
                "metadata": r.metadata if hasattr(r, "metadata") else {},
                "source": "pageindex",
            }
            for r in results
        ]

    except ImportError:
        log.warning("pageindex package not installed.")
        return []
    except Exception as e:
        log.error(f"PageIndex query failed: {e}")
        return []


def _get_or_create_index(pi) -> str | None:
    """Helper to get existing index ID or create new one."""
    try:
        indexes = pi.list_indexes()
        if indexes:
            return indexes[0].id if hasattr(indexes[0], "id") else str(indexes[0])
    except Exception:
        pass

    return upload_documents()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if not PAGEINDEX_API_KEY:
        print("⚠ PAGEINDEX_API_KEY not set in .env")
        print("  Đăng ký tại: https://pageindex.ai/")
        print("  pageindex_search() sẽ trả về [] khi không có API key (graceful fallback).")
        # Demo graceful fallback
        results = pageindex_search("hình phạt sử dụng ma tuý", top_k=3)
        print(f"\nGraceful fallback result: {results}")
    else:
        print("Testing PageIndex query...")
        results = pageindex_search("hình phạt sử dụng ma tuý", top_k=3)
        for r in results:
            print(f"[{r['score']:.3f}] [{r['source']}] {r['content'][:80]}...")
