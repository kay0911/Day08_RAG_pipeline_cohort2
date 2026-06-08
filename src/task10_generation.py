"""
Task 10 — Generation Có Citation.

Design choices:
- top_k=5: Đủ evidence mà không quá dài gây "lost in the middle"
- top_p=0.9: Nucleus sampling — đủ diverse, không quá random
- temperature=0.3: RAG cần factual, ít sáng tạo (closer to deterministic)
- Model: gpt-4o-mini (cost-effective, good context length)
  Fallback: claude-3-haiku nếu không có OpenAI key

Document reordering tránh "lost in the middle" (Liu et al. 2023):
    LLM chú ý tốt nhất tới đầu và cuối prompt.
    Input:  [1, 2, 3, 4, 5] (ranked by score, 1=best)
    Output: [1, 3, 5, 4, 2] (best at start, 2nd best at end, worst in middle)
"""

import logging
import os

os.environ.setdefault("USE_TF", "0")

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

try:
    from src.task9_retrieval_pipeline import retrieve
except ImportError:
    from task9_retrieval_pipeline import retrieve

# =============================================================================
# CONFIGURATION
# =============================================================================

TOP_K = 5       # 5 chunks: đủ evidence, không quá nhiều gây attention dilution
TOP_P = 0.9     # nucleus sampling: top 90% probability mass
TEMPERATURE = 0.3  # low temperature: factual, consistent answers

SYSTEM_PROMPT = """Answer the following question comprehensively in Vietnamese.
For every statement of fact or claim, immediately insert a citation in brackets
linking to the specific source (e.g., [Luật Phòng chống ma tuý 2021, Điều 3]
or [VnExpress, 2024]).

If the information is not explicitly stated in the provided context or knowledge
base, state 'Tôi không thể xác minh thông tin này từ nguồn hiện có' rather than
guessing.

Rules:
- Only use information from the provided context
- Every factual claim MUST have a citation
- If context is insufficient, say so clearly
- Structure your answer with clear paragraphs"""


# =============================================================================
# DOCUMENT REORDERING (tránh lost in the middle)
# =============================================================================

def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """
    Sắp xếp chunks để tránh "lost in the middle" effect.

    LLM nhớ tốt thông tin ở ĐẦU và CUỐI, quên thông tin ở GIỮA.
    Strategy: chunks quan trọng nhất (rank 1, 2) ở đầu và cuối;
    chunks ít quan trọng hơn ở giữa.

    Input (by score desc): [A, B, C, D, E]  (A=best, E=worst)
    Output:                [A, C, E, D, B]   (A first, B last, worst in middle)

    Args:
        chunks: List sorted by score descending

    Returns:
        Reordered list.
    """
    n = len(chunks)
    if n <= 2:
        return chunks

    # Place odd-indexed chunks first (0, 2, 4, ...) then even-indexed reversed (3, 1)
    # This puts best at start, second-best at end, rest in middle
    evens = chunks[::2]   # indices 0, 2, 4, ...
    odds = chunks[1::2]   # indices 1, 3, 5, ...
    return evens + list(reversed(odds))


# =============================================================================
# CONTEXT FORMATTING
# =============================================================================

def format_context(chunks: list[dict]) -> str:
    """
    Format chunks thành context string cho prompt.
    Mỗi chunk có label source để LLM có thể cite.

    Returns:
        Formatted context string.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source", f"Document {i}")
        doc_type = meta.get("type", "unknown")
        # Remove .md extension for cleaner citation
        source_label = source.replace(".md", "").replace(".docx", "").replace(".pdf", "")

        context_parts.append(
            f"[Tài liệu {i} | Nguồn: {source_label} | Loại: {doc_type}]\n"
            f"{chunk['content']}"
        )

    return "\n\n---\n\n".join(context_parts)


# =============================================================================
# GENERATION
# =============================================================================

def generate_with_citation(query: str, context_chunks: list[dict] | None = None, top_k: int = TOP_K) -> dict:
    """
    End-to-end RAG generation có citation.

    Args:
        query: Câu hỏi của user
        context_chunks: Optional pre-retrieved chunks. If None, retrieval is called.
        top_k: Số chunks đưa vào context (nếu cần retrieve)

    Returns:
        {
            'answer': str,           # Câu trả lời có citation
            'sources': list[dict],   # Các chunks đã dùng
            'retrieval_source': str  # 'hybrid' hoặc 'pageindex'
        }
    """
    # Step 1: Retrieve (nếu chưa có chunks)
    if context_chunks is None:
        context_chunks = retrieve(query, top_k=top_k)

    if not context_chunks:
        return {
            "answer": "Tôi không thể xác minh thông tin này từ nguồn hiện có — không tìm thấy tài liệu liên quan.",
            "sources": [],
            "retrieval_source": "none",
        }

    # Step 2: Reorder để tránh lost in the middle
    reordered = reorder_for_llm(context_chunks)

    # Step 3: Format context với source labels
    context = format_context(reordered)

    # Step 4: Build prompt
    user_message = f"Context:\n{context}\n\n---\n\nCâu hỏi: {query}"

    # Step 5: Call LLM
    answer = _call_llm(user_message)

    retrieval_source = context_chunks[0].get("source", "hybrid") if context_chunks else "none"

    return {
        "answer": answer,
        "sources": context_chunks,
        "retrieval_source": retrieval_source,
    }


def _call_llm(user_message: str) -> str:
    """
    Call LLM với OpenAI (fallback to Claude if no OpenAI key).
    Trả về "I cannot verify..." nếu không có API key nào.
    """
    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    if openai_key and openai_key.startswith("sk-"):
        return _call_openai(user_message, openai_key)
    elif anthropic_key:
        return _call_anthropic(user_message, anthropic_key)
    else:
        log.warning("No LLM API key found. Returning placeholder response.")
        return (
            "Tôi không thể xác minh thông tin này từ nguồn hiện có — "
            "vui lòng cấu hình OPENAI_API_KEY hoặc ANTHROPIC_API_KEY trong file .env."
        )


def _call_openai(user_message: str, api_key: str) -> str:
    """Call OpenAI ChatCompletion API."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=TEMPERATURE,
        top_p=TOP_P,
        max_tokens=1500,
    )
    return response.choices[0].message.content


def _call_anthropic(user_message: str, api_key: str) -> str:
    """Call Anthropic Claude API."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_queries = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý theo pháp luật Việt Nam?",
        "Những nghệ sĩ nào đã bị bắt vì liên quan tới ma tuý?",
    ]

    for q in test_queries:
        print(f"\n{'='*70}")
        print(f"Q: {q}")
        print("=" * 70)
        result = generate_with_citation(q)
        print(f"\nA: {result['answer']}")
        print(f"\n[Sources: {len(result['sources'])} chunks | via {result['retrieval_source']}]")
