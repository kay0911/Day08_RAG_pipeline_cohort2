from pathlib import Path
import os
import sys

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.task9_retrieval_pipeline import retrieve
from src.task10_generation import format_context, generate_with_citation, reorder_for_llm

st.set_page_config(
    page_title="RAG Chatbot - Legal & News Search Engine",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .stApp { background-color: #0d0f12; color: #e2e8f0; font-family: 'Inter', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 50%, #06b6d4 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 2.8rem; font-weight: 800; margin-bottom: 0.2rem; letter-spacing: -0.05em;
    }
    .sub-header { font-size: 1.05rem; color: #94a3b8; margin-bottom: 1.5rem; }
    .chat-bubble { padding: 1rem 1.2rem; border-radius: 1rem; margin-bottom: 1rem; line-height: 1.6; border: 1px solid #1e293b; }
    .user-bubble { background-color: #1e293b; color: #f8fafc; border-left: 5px solid #3b82f6; }
    .assistant-bubble { background-color: #0f172a; color: #e2e8f0; border-left: 5px solid #10b981; }
    .source-card { background-color: #1e293b; padding: 1rem; border-radius: 0.5rem; border: 1px solid #334155; margin-bottom: 0.75rem; }
    [data-testid="stSidebar"] { background-color: #090d16; border-right: 1px solid #1e293b; }
</style>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("<h2 style='color: #3b82f6;'>⚙️ Cấu Hình Hệ Thống</h2>", unsafe_allow_html=True)
    use_rerank = st.toggle("Kích hoạt Reranking", value=True)
    score_threshold = st.slider("Ngưỡng điểm retrieval", 0.0, 1.0, 0.3, 0.05)
    top_k = st.slider("Số lượng context chọn", 1, 10, 5)
    st.markdown("---")
    st.markdown("<h3 style='color: #10b981;'>📂 Tài Liệu Đã Index</h3>", unsafe_allow_html=True)
    st.write("- Bộ luật Hình sự 2015")
    st.write("- Luật Phòng, chống ma tuý 2021")
    st.write("- Nghị định 105/2021/NĐ-CP")
    st.write("- Tin tức báo chí nghệ sĩ và chất cấm")

st.markdown("<h1 class='main-header'>🛡️ DrugLaw RAG Chatbot</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-header'>Hệ thống hỏi đáp về luật ma tuý và tin tức liên quan, trả lời có trích dẫn nguồn.</p>", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    role_class = "user-bubble" if msg["role"] == "user" else "assistant-bubble"
    role_label = "👤 Bạn" if msg["role"] == "user" else "🤖 Trợ Lý"
    st.markdown(f"<div class='chat-bubble {role_class}'><strong>{role_label}</strong><br/>{msg['content']}</div>", unsafe_allow_html=True)

query = st.chat_input("Nhập câu hỏi của bạn về luật hoặc tin tức ma tuý...")

if query:
    st.session_state.messages.append({"role": "user", "content": query})
    st.markdown(f"<div class='chat-bubble user-bubble'><strong>👤 Bạn</strong><br/>{query}</div>", unsafe_allow_html=True)

    with st.spinner("Đang tìm kiếm và xử lý câu trả lời..."):
        chunks = retrieve(query, top_k=top_k, score_threshold=score_threshold, use_reranking=use_rerank)
        reordered = reorder_for_llm(chunks)
        context_str = format_context(reordered)
        result = generate_with_citation(query, top_k=top_k, context_chunks=reordered)
        answer = result["answer"] if result.get("answer") else "I cannot verify this information"
        if not answer and context_str:
            answer = context_str[:500]

        st.markdown(f"<div class='chat-bubble assistant-bubble'><strong>🤖 Trợ Lý</strong><br/>{answer}</div>", unsafe_allow_html=True)
        st.session_state.messages.append({"role": "assistant", "content": answer})

        if reordered:
            with st.expander("📄 Nguồn tài liệu trích dẫn (Đã tìm thấy)"):
                for idx, c in enumerate(reordered, 1):
                    source_name = c.get("metadata", {}).get("source", "Chưa rõ")
                    score_val = c.get("score", 0.0)
                    source_type = c.get("metadata", {}).get("type", "unknown").upper()
                    source_method = c.get("source", "hybrid").upper()
                    st.markdown(
                        f"""
                    <div class='source-card'>
                        <strong>Document {idx}: {source_name}</strong> | Type: <span style='color: #10b981;'>{source_type}</span> | Method: <span style='color: #3b82f6;'>{source_method}</span> | Score: <span style='color: #f59e0b;'>{score_val:.3f}</span>
                        <p style='color: #cbd5e1; margin-top: 0.5rem;'>{c['content']}</p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )