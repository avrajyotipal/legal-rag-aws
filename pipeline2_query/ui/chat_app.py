"""
Streamlit chat UI for Pipeline 2.
Users ask legal questions; answers are grounded in indexed documents with citations.
Run: streamlit run pipeline2_query/ui/chat_app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline2_query.query_pipeline import run_query

st.set_page_config(
    page_title="Legal Research Assistant",
    page_icon="⚖",
    layout="wide",
)

st.title("Legal Research Assistant")
st.caption("Answers are generated from uploaded legal documents only, with full citations.")
st.markdown("---")


def _render_citations(citations: list[dict]) -> None:
    with st.expander(f"Sources ({len(citations)})"):
        for cit in citations:
            line = f"**[Source {cit['index']}]** `{cit['source_file']}`"
            if cit.get("page"):
                line += f" — Page {cit['page']}"
            if cit.get("section"):
                line += f" | {cit['section']}"
            if cit.get("score"):
                line += f" *(relevance: {cit['score']:.2%})*"
            st.markdown(line)


# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Replay chat history ───────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations"):
            _render_citations(msg["citations"])

# ── Chat input ────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask a legal question..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Searching documents and generating answer..."):
            result = run_query(prompt)

        st.markdown(result["answer"])
        if result.get("citations"):
            _render_citations(result["citations"])

    st.session_state.messages.append({
        "role":      "assistant",
        "content":   result["answer"],
        "citations": result.get("citations", []),
    })
