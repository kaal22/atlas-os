#!/usr/bin/env python3
"""Atlas Knowledge Service — ingest, chunk, embed, Qdrant + hybrid search."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

EMBED_MODEL = os.environ.get("ATLAS_EMBED_MODEL", "nomic-embed-text")
COLLECTION = os.environ.get("ATLAS_QDRANT_COLLECTION", "atlas_knowledge")
VECTOR_SIZE = int(os.environ.get("ATLAS_EMBED_DIM", "768"))
QDRANT_URL = os.environ.get("ATLAS_QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
OLLAMA_URL = os.environ.get("ATLAS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
# Pack-installed corpus is ingested as user_id "system" and is readable by every account.
SHARED_KNOWLEDGE_USERS = frozenset({"system"})

TEXT_EXTENSIONS = {".md", ".txt", ".markdown", ".rst", ".csv", ".json", ".org", ".html", ".htm"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        i += max(1, size - overlap)
    return chunks


def scrub_prompt_injection(text: str) -> str:
    text = re.sub(r"(?i)ignore (all|previous) instructions", "[filtered]", text)
    text = re.sub(r"(?i)system\s*:\s*", "[filtered]: ", text)
    return text


def extract_text(path: Path) -> str:
    """Extract plain text from supported document types."""
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if suffix in {".html", ".htm"}:
            raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
            raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
            raw = re.sub(r"(?s)<[^>]+>", " ", raw)
        return scrub_prompt_injection(raw)

    if suffix in PDF_EXTENSIONS:
        # Prefer poppler pdftotext (no Python deps).
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", "-nopgbrk", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return scrub_prompt_injection(proc.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            parts = [(page.extract_text() or "") for page in reader.pages]
            joined = "\n".join(parts)
            if joined.strip():
                return scrub_prompt_injection(joined)
        except Exception:
            pass
        raise ValueError("pdf_extract_failed")

    raise ValueError("unsupported_file_type")


def _http_json(method: str, url: str, body: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {e.code}: {detail or e.reason}") from e


def ollama_reachable(host: str = OLLAMA_URL) -> bool:
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=2) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def embed_model_installed(host: str = OLLAMA_URL, tag: str = EMBED_MODEL) -> bool:
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [m.get("name", "") for m in data.get("models", [])]
        return any(n == tag or n.startswith(tag) or tag in n for n in names)
    except Exception:
        return False


def embed_texts(texts: list[str], host: str = OLLAMA_URL, model: str = EMBED_MODEL) -> list[list[float]]:
    out: list[list[float]] = []
    for text in texts:
        data = _http_json(
            "POST",
            host + "/api/embeddings",
            {"model": model, "prompt": text[:8000]},
            timeout=120.0,
        )
        vec = data.get("embedding")
        if not isinstance(vec, list) or not vec:
            raise RuntimeError("empty_embedding")
        out.append([float(x) for x in vec])
    return out


def qdrant_reachable(url: str = QDRANT_URL) -> bool:
    try:
        with urllib.request.urlopen(url + "/readyz", timeout=2) as resp:
            return 200 <= resp.status < 300
    except Exception:
        try:
            with urllib.request.urlopen(url + "/collections", timeout=2) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False


def _point_id(doc_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"atlas:{doc_id}:{chunk_index}"))


@dataclass
class DocumentRecord:
    doc_id: str
    user_id: str
    path: str
    chunks: list[str] = field(default_factory=list)
    name: str = ""
    trust: str = "user_document"
    vectorized: bool = False
    created_at: float = 0.0


@dataclass
class KnowledgeService:
    root: Path
    docs: dict[str, DocumentRecord] = field(default_factory=dict)
    qdrant_url: str = QDRANT_URL
    ollama_url: str = OLLAMA_URL
    keyword_only: bool = False

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        if os.environ.get("ATLAS_KNOWLEDGE_KEYWORD_ONLY") == "1":
            self.keyword_only = True
        if self.index_path.exists():
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            for d in raw.get("docs", []):
                self.docs[d["doc_id"]] = DocumentRecord(
                    doc_id=d["doc_id"],
                    user_id=d["user_id"],
                    path=d["path"],
                    chunks=d.get("chunks") or [],
                    name=d.get("name") or Path(d["path"]).name,
                    trust=d.get("trust") or "user_document",
                    vectorized=bool(d.get("vectorized")),
                    created_at=float(d.get("created_at") or 0),
                )

    def save(self) -> None:
        payload = {
            "docs": [
                {
                    "doc_id": d.doc_id,
                    "user_id": d.user_id,
                    "path": d.path,
                    "chunks": d.chunks,
                    "name": d.name,
                    "trust": d.trust,
                    "vectorized": d.vectorized,
                    "created_at": d.created_at,
                }
                for d in self.docs.values()
            ]
        }
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def status(self) -> dict[str, Any]:
        q_ok = False if self.keyword_only else qdrant_reachable(self.qdrant_url)
        o_ok = False if self.keyword_only else ollama_reachable(self.ollama_url)
        emb_ok = False if self.keyword_only else embed_model_installed(self.ollama_url)
        mode = "keyword"
        if q_ok and emb_ok:
            mode = "hybrid"
        elif not self.keyword_only and (q_ok or emb_ok):
            mode = "degraded"
        return {
            "qdrant": q_ok,
            "ollama": o_ok,
            "embed_model": EMBED_MODEL,
            "embed_ready": emb_ok,
            "mode": mode,
            "docs": len(self.docs),
            "hint": (
                None
                if mode == "hybrid" or self.keyword_only
                else (
                    f"Download embeddings model {EMBED_MODEL} in Models for semantic search."
                    if o_ok and not emb_ok
                    else "Qdrant or Ollama unavailable — keyword search only."
                )
            ),
        }

    def ensure_collection(self, vector_size: int = VECTOR_SIZE) -> None:
        try:
            _http_json("GET", f"{self.qdrant_url}/collections/{COLLECTION}", timeout=5)
            return
        except Exception:
            pass
        _http_json(
            "PUT",
            f"{self.qdrant_url}/collections/{COLLECTION}",
            {"vectors": {"size": vector_size, "distance": "Cosine"}},
            timeout=10,
        )

    def _delete_qdrant_doc(self, doc_id: str) -> None:
        if not qdrant_reachable(self.qdrant_url):
            return
        try:
            _http_json(
                "POST",
                f"{self.qdrant_url}/collections/{COLLECTION}/points/delete",
                {"filter": {"must": [{"key": "doc_id", "match": {"value": doc_id}}]}},
                timeout=15,
            )
        except Exception:
            pass

    def _upsert_vectors(self, rec: DocumentRecord, vectors: list[list[float]]) -> None:
        self.ensure_collection(len(vectors[0]) if vectors else VECTOR_SIZE)
        points = []
        for idx, (chunk, vec) in enumerate(zip(rec.chunks, vectors)):
            points.append(
                {
                    "id": _point_id(rec.doc_id, idx),
                    "vector": vec,
                    "payload": {
                        "user_id": rec.user_id,
                        "doc_id": rec.doc_id,
                        "path": rec.path,
                        "name": rec.name,
                        "chunk_index": idx,
                        "text": chunk,
                        "trust": rec.trust,
                    },
                }
            )
        # Batch in chunks of 32
        for i in range(0, len(points), 32):
            _http_json(
                "PUT",
                f"{self.qdrant_url}/collections/{COLLECTION}/points?wait=true",
                {"points": points[i : i + 32]},
                timeout=120,
            )

    @staticmethod
    def _doc_visible(user_id: str, doc_user_id: str) -> bool:
        return doc_user_id == user_id or doc_user_id in SHARED_KNOWLEDGE_USERS

    def ingest_file(self, user_id: str, path: Path, *, trust: str = "user_document") -> DocumentRecord:
        path = Path(path)
        text = extract_text(path)
        if not text.strip():
            raise ValueError("empty_document")
        doc_id = hashlib.sha256(f"{user_id}:{path.resolve()}".encode()).hexdigest()[:16]
        # Replace prior vectors for this doc
        if doc_id in self.docs:
            self._delete_qdrant_doc(doc_id)
        rec = DocumentRecord(
            doc_id=doc_id,
            user_id=user_id,
            path=str(path.resolve()) if path.exists() else str(path),
            chunks=chunk_text(text),
            name=path.name,
            trust=trust or "user_document",
            vectorized=False,
            created_at=time.time(),
        )
        if not rec.chunks:
            raise ValueError("empty_document")

        st = self.status()
        if not self.keyword_only and st["qdrant"] and st["embed_ready"]:
            try:
                vectors = embed_texts(rec.chunks, host=self.ollama_url)
                self._upsert_vectors(rec, vectors)
                rec.vectorized = True
            except Exception:
                rec.vectorized = False

        self.docs[doc_id] = rec
        self.save()
        return rec

    def delete_document(self, user_id: str, doc_id: str) -> bool:
        rec = self.docs.get(doc_id)
        if not rec or rec.user_id != user_id:
            return False
        self._delete_qdrant_doc(doc_id)
        del self.docs[doc_id]
        self.save()
        return True

    def get_chunk(self, user_id: str, doc_id: str, chunk_index: int) -> dict[str, Any] | None:
        rec = self.docs.get(doc_id)
        if not rec or not self._doc_visible(user_id, rec.user_id):
            return None
        if chunk_index < 0 or chunk_index >= len(rec.chunks):
            return None
        return {
            "doc_id": rec.doc_id,
            "path": rec.path,
            "name": rec.name,
            "chunk_index": chunk_index,
            "text": rec.chunks[chunk_index],
            "trust": rec.trust,
            "total_chunks": len(rec.chunks),
        }

    def library(self, user_id: str) -> list[dict[str, Any]]:
        docs = [d for d in self.docs.values() if self._doc_visible(user_id, d.user_id)]
        docs.sort(key=lambda d: d.name.lower())
        return [
            {
                "doc_id": d.doc_id,
                "name": d.name or Path(d.path).name,
                "path": d.path,
                "chunks": len(d.chunks),
                "vectorized": d.vectorized,
                "trust": d.trust,
                "user_id": d.user_id,
            }
            for d in docs
        ]

    def _keyword_search(self, user_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        q = [t for t in query.lower().split() if t]
        hits: list[dict[str, Any]] = []
        for doc in self.docs.values():
            if not self._doc_visible(user_id, doc.user_id):
                continue
            for idx, chunk in enumerate(doc.chunks):
                score = sum(1 for t in q if t in chunk.lower()) if q else 0
                if score > 0:
                    hits.append(
                        {
                            "doc_id": doc.doc_id,
                            "path": doc.path,
                            "name": doc.name or Path(doc.path).name,
                            "chunk_index": idx,
                            "text": chunk,
                            "score": float(score),
                            "trust": doc.trust,
                            "source": "keyword",
                        }
                    )
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:limit]

    def _vector_search(self, user_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        vectors = embed_texts([query], host=self.ollama_url)
        should = [{"key": "user_id", "match": {"value": user_id}}]
        for shared in SHARED_KNOWLEDGE_USERS:
            should.append({"key": "user_id", "match": {"value": shared}})
        data = _http_json(
            "POST",
            f"{self.qdrant_url}/collections/{COLLECTION}/points/search",
            {
                "vector": vectors[0],
                "limit": limit,
                "with_payload": True,
                "filter": {"should": should},
            },
            timeout=60,
        )
        hits: list[dict[str, Any]] = []
        for row in data.get("result") or []:
            payload = row.get("payload") or {}
            if not self._doc_visible(user_id, str(payload.get("user_id") or "")):
                continue
            hits.append(
                {
                    "doc_id": payload.get("doc_id"),
                    "path": payload.get("path"),
                    "name": payload.get("name") or Path(str(payload.get("path") or "")).name,
                    "chunk_index": int(payload.get("chunk_index") or 0),
                    "text": payload.get("text") or "",
                    "score": float(row.get("score") or 0),
                    "trust": payload.get("trust") or "user_document",
                    "source": "vector",
                }
            )
        return hits

    def search(self, user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        kw = self._keyword_search(user_id, query, limit=limit * 2)
        vec: list[dict[str, Any]] = []
        st = self.status()
        if not self.keyword_only and st["mode"] in {"hybrid", "degraded"} and st["qdrant"] and st["embed_ready"]:
            try:
                vec = self._vector_search(user_id, query, limit=limit)
            except Exception:
                vec = []

        # Merge by (doc_id, chunk_index); prefer higher score; mark hybrid when both.
        merged: dict[tuple[str, int], dict[str, Any]] = {}
        for h in kw + vec:
            key = (str(h.get("doc_id")), int(h.get("chunk_index") or 0))
            prev = merged.get(key)
            if not prev or float(h.get("score") or 0) > float(prev.get("score") or 0):
                item = dict(h)
                if prev and prev.get("source") != h.get("source"):
                    item["source"] = "hybrid"
                merged[key] = item
        hits = sorted(merged.values(), key=lambda h: float(h.get("score") or 0), reverse=True)
        relevant: list[dict[str, Any]] = []
        for h in hits:
            score = float(h.get("score") or 0)
            src = str(h.get("source") or "keyword")
            if src == "keyword" and score < 1.0:
                continue
            if src in {"vector", "hybrid"} and score < 0.52:
                continue
            relevant.append(h)
        return relevant[:limit]

    def backup(self, dest_dir: Path) -> dict[str, Any]:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        archive = dest / f"knowledge-{stamp}.tar.gz"
        staging = dest / f".stage-{stamp}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        # Copy JSON index + chunk store
        if self.index_path.exists():
            shutil.copy2(self.index_path, staging / "index.json")
        meta = {"created_at": time.time(), "docs": len(self.docs), "collection": COLLECTION}
        (staging / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        # Best-effort Qdrant snapshot via API
        qsnap_name = None
        if qdrant_reachable(self.qdrant_url):
            try:
                snap = _http_json(
                    "POST",
                    f"{self.qdrant_url}/collections/{COLLECTION}/snapshots",
                    {},
                    timeout=60,
                )
                qsnap_name = (snap.get("result") or {}).get("name")
                meta["qdrant_snapshot"] = qsnap_name
                (staging / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            except Exception as e:
                meta["qdrant_error"] = str(e)
                (staging / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        with tarfile.open(archive, "w:gz") as tar:
            for p in staging.iterdir():
                tar.add(p, arcname=p.name)
        shutil.rmtree(staging, ignore_errors=True)
        return {"ok": True, "archive": str(archive), "qdrant_snapshot": qsnap_name, "docs": len(self.docs)}

    def restore(self, archive_path: Path) -> dict[str, Any]:
        archive = Path(archive_path)
        if not archive.is_file():
            raise FileNotFoundError(str(archive))
        staging = self.root / ".restore-tmp"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(staging)
        idx = staging / "index.json"
        if not idx.exists():
            raise ValueError("backup_missing_index")
        shutil.copy2(idx, self.index_path)
        self.docs.clear()
        self.__post_init__()
        # Re-vectorize if services available
        revec = 0
        st = self.status()
        if st["qdrant"] and st["embed_ready"]:
            for doc_id, rec in list(self.docs.items()):
                try:
                    self._delete_qdrant_doc(doc_id)
                    vectors = embed_texts(rec.chunks, host=self.ollama_url)
                    self._upsert_vectors(rec, vectors)
                    rec.vectorized = True
                    revec += 1
                except Exception:
                    rec.vectorized = False
            self.save()
        shutil.rmtree(staging, ignore_errors=True)
        return {"ok": True, "docs": len(self.docs), "revectorized": revec}


if __name__ == "__main__":
    import tempfile

    os.environ["ATLAS_KNOWLEDGE_KEYWORD_ONLY"] = "1"
    with tempfile.TemporaryDirectory() as td:
        ks = KnowledgeService(Path(td), keyword_only=True)
        p = Path(td) / "sample.md"
        p.write_text("Atlas OS is an offline-first AI operating environment.", encoding="utf-8")
        ks.ingest_file("u1", p)
        print(ks.search("u1", "offline AI"))
        assert ks.search("u2", "offline AI") == []
        assert ks.get_chunk("u1", list(ks.docs)[0], 0)
        print("OK knowledge_service smoke")
