#!/usr/bin/env python3
"""
Contextual Workspace RAG for JARVIS 2.0
Indexes local folders (Markdown, TXT, Code, PDFs) for grounded question-answering.
Provides semantic chunking, keyword-density scoring, and LLM synthesis.
"""

import math
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import BASE_DIR, load_vault, save_vault
from core.llm_router import router


class WorkspaceRAG:
    """
    Local document search and retrieval-augmented generation engine.
    """

    SUPPORTED_EXTENSIONS = {".md", ".txt", ".py", ".json", ".js", ".ts", ".html", ".css", ".rst", ".pdf"}

    def __init__(self):
        self._lock = threading.Lock()
        self._chunks: List[Dict[str, Any]] = []
        self._indexed_files_count: int = 0
        self._last_index_time: float = 0.0

    def get_workspace_path(self) -> Path:
        """Returns the active workspace directory."""
        vault = load_vault()
        custom_path = vault.get("workspace_path", "").strip()
        if custom_path and Path(custom_path).exists():
            return Path(custom_path)
        return BASE_DIR

    def set_workspace_path(self, path_str: str) -> bool:
        """Sets a new workspace folder path in api_vault.json."""
        p = Path(path_str.strip())
        if not p.exists() or not p.is_dir():
            return False
        vault = load_vault()
        vault["workspace_path"] = str(p.resolve())
        save_vault(vault)
        self.index_workspace(p)
        return True

    def index_workspace(self, root_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Scans workspace directory, chunks documents, and builds the retrieval index.
        """
        target_dir = root_dir or self.get_workspace_path()
        chunks: List[Dict[str, Any]] = []
        files_indexed = 0

        for root, dirs, files in os.walk(target_dir):
            # Skip hidden and cache folders
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "dist", "build")]

            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    continue

                try:
                    text = self._read_file_text(file_path, ext)
                    if not text or len(text.strip()) < 10:
                        continue

                    file_chunks = self._chunk_text(text, str(file_path), chunk_size=800, overlap=150)
                    chunks.extend(file_chunks)
                    files_indexed += 1
                except Exception as e:
                    print(f"[WorkspaceRAG] Error reading {file_path}: {e}")

        with self._lock:
            self._chunks = chunks
            self._indexed_files_count = files_indexed
            self._last_index_time = os.times().elapsed

        print(f"[WorkspaceRAG] Indexed {files_indexed} files into {len(chunks)} searchable chunks.")
        return {
            "ok": True,
            "workspace_path": str(target_dir),
            "files_indexed": files_indexed,
            "chunks_count": len(chunks),
        }

    def _read_file_text(self, file_path: Path, ext: str) -> str:
        """Extract text from plain text or PDF files."""
        if ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(file_path))
                pages_text = [page.extract_text() or "" for page in reader.pages]
                return "\n".join(pages_text)
            except Exception:
                return ""

        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    def _chunk_text(self, text: str, source_path: str, chunk_size: int = 800, overlap: int = 150) -> List[Dict[str, Any]]:
        """Split text into overlapping windows with line number tracking."""
        lines = text.split("\n")
        chunks: List[Dict[str, Any]] = []

        current_lines: List[str] = []
        current_len = 0
        start_line = 1

        for idx, line in enumerate(lines, start=1):
            current_lines.append(line)
            current_len += len(line) + 1

            if current_len >= chunk_size:
                chunk_str = "\n".join(current_lines)
                chunks.append({
                    "source": source_path,
                    "filename": Path(source_path).name,
                    "start_line": start_line,
                    "end_line": idx,
                    "text": chunk_str,
                })
                # Retain overlap lines
                overlap_lines = max(1, int(len(current_lines) * (overlap / chunk_size)))
                current_lines = current_lines[-overlap_lines:]
                current_len = sum(len(l) + 1 for l in current_lines)
                start_line = idx - len(current_lines) + 1

        if current_lines:
            chunk_str = "\n".join(current_lines)
            chunks.append({
                "source": source_path,
                "filename": Path(source_path).name,
                "start_line": start_line,
                "end_line": len(lines),
                "text": chunk_str,
            })

        return chunks

    def search(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """
        Scores indexed chunks against query keywords using term frequency and density.
        """
        with self._lock:
            chunks = list(self._chunks)

        if not chunks:
            self.index_workspace()
            with self._lock:
                chunks = list(self._chunks)

        if not chunks:
            return []

        query_tokens = [tok.lower() for tok in re.findall(r"\w+", query) if len(tok) > 2]
        if not query_tokens:
            return chunks[:top_k]

        scored: List[Tuple[float, Dict[str, Any]]] = []

        for ch in chunks:
            text_lower = ch["text"].lower()
            score = 0.0

            for tok in query_tokens:
                count = text_lower.count(tok)
                if count > 0:
                    score += 1.0 + math.log(1.0 + count)

            # Bonus for filename match
            fn_lower = ch["filename"].lower()
            if any(tok in fn_lower for tok in query_tokens):
                score += 3.0

            if score > 0.0:
                scored.append((score, ch))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    def query(self, user_question: str) -> Dict[str, Any]:
        """
        RAG Pipeline: Search relevant workspace snippets and synthesize grounded answer.
        """
        snippets = self.search(user_question, top_k=4)
        if not snippets:
            return {
                "ok": True,
                "answer": "I found no relevant documents in your current workspace for this question, sir.",
                "snippets": [],
            }

        context_blocks = []
        for i, s in enumerate(snippets, start=1):
            context_blocks.append(
                f"[Document {i}]: {s['filename']} (lines {s['start_line']}-{s['end_line']})\n{s['text']}"
            )

        context_str = "\n\n---\n\n".join(context_blocks)

        system_prompt = (
            "You are JARVIS. Answer the user question accurately and concisely using ONLY the provided workspace excerpts.\n"
            "Cite the source filenames when referring to specific information."
        )
        prompt = f"Workspace Context:\n{context_str}\n\nUser Question: {user_question}"

        answer = router.query_text("qa_chat", prompt, system_prompt=system_prompt)

        return {
            "ok": True,
            "answer": answer or "Analysis complete.",
            "snippets": snippets,
        }


# Global workspace RAG singleton
workspace_rag = WorkspaceRAG()
