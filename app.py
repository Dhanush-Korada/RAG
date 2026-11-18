import os, io, json, time, base64, re
from pathlib import Path

import streamlit as st
from pypdf import PdfReader
from google import genai
from google.genai import types
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv

load_dotenv()
try:
    import pyttsx3
except Exception:
    pyttsx3 = None

st.set_page_config(page_title="Doc Retrieval Agent", page_icon="🎙️", layout="wide")

MODEL = "gemini-3.8-flash"
FALLBACK = "This information is not mentioned in the document. Please contact the team."

if "chunks" not in st.session_state:
    st.session_state.chunks = []
if "doc_name" not in st.session_state:
    st.session_state.doc_name = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent_running" not in st.session_state:
    st.session_state.agent_running = False
if "started_at" not in st.session_state:
    st.session_state.started_at = 0

def extract_pdf(file_bytes):
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page_no, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            # Keep page identity so the UI can highlight the exact source page.
            words = text.split()
            step = 180
            for i in range(0, len(words), step):
                chunk = " ".join(words[i:i+step])
                pages.append({"page": page_no, "text": chunk})
    return pages

def retrieve(question, chunks, k=4):
    if not chunks:
        return []
    corpus = [x["text"] for x in chunks]
    vectorizer = TfidfVectorizer(stop_words="english")
    try:
        matrix = vectorizer.fit_transform(corpus + [question])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        ids = scores.argsort()[::-1][:k]
        return [dict(chunks[i], score=float(scores[i])) for i in ids if scores[i] > 0.02]
    except Exception:
        return []

def ask_gemini(question, sources):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=key)
    context = "\n\n".join(
        f"[SOURCE {i+1} | PAGE {s['page']}]\n{s['text']}"
        for i, s in enumerate(sources)
    )

    prompt = f"""
You are a strict document-only retrieval agent.

RULES:
1. Answer ONLY using the supplied DOCUMENT SOURCES.
2. Do not use general knowledge, web knowledge, guesses, or assumptions.
3. If the answer is not clearly supported by the sources, return exactly:
   {FALLBACK}
4. Keep the answer natural and concise for voice.
5. If answering from a source, also return the exact source sentence(s) used.
6. Return valid JSON only with these keys:
   answer, source_text, page, found
7. found must be true only when the answer is explicitly supported.

DOCUMENT SOURCES:
{context}

USER QUESTION:
{question}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    raw = response.text.strip()
    data = json.loads(raw)

    if not data.get("found") or data.get("answer") == FALLBACK:
        return {"answer": FALLBACK, "source_text": "", "page": None, "found": False}

    return data



# ---------- CSS ----------
st.markdown("""
<style>
.block-container {padding-top: 1rem; max-width: 1400px;}
.topbar {display:flex; justify-content:space-between; align-items:center;
         padding:14px 20px; border-bottom:1px solid #e5e7eb; margin-bottom:15px;}
.brand {font-size:22px; font-weight:700;}
.nav {color:#64748b; font-weight:600;}
.docbox {border:1px solid #e5e7eb; border-radius:16px; padding:22px;
         background:#fff; min-height:520px; line-height:1.8;}
.highlight {background:#fff19a; padding:4px 7px; border-radius:6px;
            box-shadow:0 0 0 2px #f4d35e55;}
.sourcecard {border-left:4px solid #f4d35e; padding:12px 16px;
             background:#fffbeb; border-radius:8px; margin:8px 0;}
.agent {border:1px solid #e5e7eb; border-radius:20px; padding:18px;
        background:#f8fafc; text-align:center;}
.timer {font-size:30px; font-weight:700;}
.small {font-size:13px; color:#64748b;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="topbar"><div class="brand">📄 Doc Retrieval</div><div class="nav">Home &nbsp;&nbsp; <b>Doc (Q/A)</b></div></div>', unsafe_allow_html=True)

left, right = st.columns([2.4, 1])

with left:
    st.subheader("Doc (Q/A)")
    uploaded = st.file_uploader("Upload a PDF document", type=["pdf"])

    if uploaded:
        data = uploaded.getvalue()
        if st.session_state.doc_name != uploaded.name:
            st.session_state.chunks = extract_pdf(data)
            st.session_state.doc_name = uploaded.name
            st.session_state.messages = []

    if st.session_state.chunks:
        st.caption(f"📄 {st.session_state.doc_name} · {len(st.session_state.chunks)} searchable sections")

        latest = None
        if st.session_state.messages:
            latest = st.session_state.messages[-1]

        # Show document text with latest answer source highlighted.
        html = []
        for c in st.session_state.chunks:
            txt = c["text"]
            if latest and latest.get("found") and c["page"] == latest.get("page"):
                source = latest.get("source_text", "").strip()
                if source and source.lower() in txt.lower():
                    # Case-insensitive-ish exact substring highlight.
                    idx = txt.lower().find(source.lower())
                    original = txt[idx:idx+len(source)]
                    txt = txt[:idx] + f'<span class="highlight">{original}</span>' + txt[idx+len(source):]
            html.append(f'<div><b>Page {c["page"]}</b><br>{txt}</div><hr>')
        st.markdown('<div class="docbox">' + "".join(html) + '</div>', unsafe_allow_html=True)

        
with right:
    st.subheader("Retrieval Agent")

    if not st.session_state.chunks:
        st.info("Upload a PDF first. The agent will answer only from that document.")
    else:
        elapsed = int(time.time() - st.session_state.started_at) if st.session_state.agent_running else 0
        elapsed = min(elapsed, 310)

        
        st.markdown("""
            <div class="agent">
              <div style="font-size:34px">🤖</div>
              <b>Retrieval Agent</b><br>
              <span class="small">Ask questions and hear document-grounded answers.</span>
            </div>
            """, unsafe_allow_html=True)

        
       
        q = st.text_input("Ask about this document", placeholder="e.g. Explain the incident response section")
        if st.button("Ask", type="primary", use_container_width=True) and q:
                    sources = retrieve(q, st.session_state.chunks)
                    if not sources:
                        result = {"answer": FALLBACK, "source_text": "", "page": None, "found": False}
                    else:
                        try:
                            result = ask_gemini(q, sources)
                        except Exception as e:
                            st.error(str(e))
                            result = None
                    if result:
                        st.session_state.messages.append({"question": q, **result})
                        st.rerun()
        
        if st.session_state.messages:
                    st.markdown("### Conversation")
                    for m in reversed(st.session_state.messages[-6:]):
                        st.markdown(f"**You:** {m['question']}")
                        st.markdown(f"**🤖 Agent:** {m['answer']}")
                        if m.get("found"):
                            st.caption(f"Highlighted source · Page {m['page']}")
        

        st.caption("Strict mode: answers must be supported by the uploaded document.")
