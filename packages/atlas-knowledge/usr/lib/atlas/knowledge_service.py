#!/usr/bin/env python3
"""Atlas Knowledge Service — ingest, chunk, embed stub, search with sources."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        i += max(1, size - overlap)
    return chunks


@dataclass
class DocumentRecord:
    doc_id: str
    user_id: str
    path: str
    chunks: list[str] = field(default_factory=list)


@dataclass
class KnowledgeService:
    root: Path
    docs: dict[str, DocumentRecord] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        if self.index_path.exists():
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            for d in raw.get("docs", []):
                self.docs[d["doc_id"]] = DocumentRecord(**d)

    def save(self) -> None:
        payload = {
            "docs": [
                {
                    "doc_id": d.doc_id,
                    "user_id": d.user_id,
                    "path": d.path,
                    "chunks": d.chunks,
                }
                for d in self.docs.values()
            ]
        }
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def ingest_file(self, user_id: str, path: Path) -> DocumentRecord:
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Strip simple prompt-injection instruction patterns from retrieved content markers
        text = re.sub(r"(?i)ignore (all|previous) instructions", "[filtered]", text)
        doc_id = hashlib.sha256(f"{user_id}:{path}".encode()).hexdigest()[:16]
        rec = DocumentRecord(doc_id=doc_id, user_id=user_id, path=str(path), chunks=chunk_text(text))
        self.docs[doc_id] = rec
        self.save()
        return rec

    def search(self, user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q = query.lower().split()
        hits: list[dict[str, Any]] = []
        for doc in self.docs.values():
            if doc.user_id != user_id:
                continue
            for idx, chunk in enumerate(doc.chunks):
                score = sum(1 for t in q if t in chunk.lower())
                if score:
                    hits.append(
                        {
                            "doc_id": doc.doc_id,
                            "path": doc.path,
                            "chunk_index": idx,
                            "text": chunk,
                            "score": score,
                            "trust": "user_document",
                        }
                    )
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:limit]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        ks = KnowledgeService(Path(td))
        p = Path(td) / "sample.md"
        p.write_text("Atlas OS is an offline-first AI operating environment.", encoding="utf-8")
        ks.ingest_file("u1", p)
        print(ks.search("u1", "offline AI"))
        assert ks.search("u2", "offline AI") == []
