"""Phase 2 — R3 (Strategy) runner.

Loads the 10 Shopee policy files from data/ecommerce/, chunks them with
HeadingChunker, then runs the 5 benchmark queries and prints/saves the
results. Retrieval uses an in-memory cosine-sim implementation on top of
the mock embedder so the script runs end-to-end without depending on the
EmbeddingStore / KnowledgeBaseAgent implementations (which are Giai đoạn 1
tasks belonging to R1 / R2 and may still be TODO).
"""
from __future__ import annotations

import io
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Force UTF-8 on stdout/stderr so print() can render Vietnamese text on Windows.
# sys.stdout.reconfigure is not always honoured by the launcher; wrap it explicitly.
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

from src.chunking import HeadingChunker
from src.embeddings import _mock_embed
from src.models import Document


DATA_DIR = Path("data/ecommerce")
RESULTS_PATH = Path("data/phase2_r3_results.json")
TOP_K = 3


@dataclass
class IndexedChunk:
    chunk_id: str  # "{doc_id}::chunk_{i}"
    doc_id: str
    heading: str
    content: str
    metadata: dict
    embedding: list[float]


def parse_front_matter(raw: str) -> tuple[dict, str]:
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    fm_block, body = parts[1], parts[2]
    fm = {}
    for line in fm_block.strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm, body


def load_documents(data_dir: Path) -> list[Document]:
    docs: list[Document] = []
    for p in sorted(data_dir.glob("*.md")):
        raw = p.read_text(encoding="utf-8")
        fm, body = parse_front_matter(raw)
        docs.append(
            Document(
                id=fm.get("doc_id", p.stem),
                content=body.strip(),
                metadata={
                    "title": fm.get("title", ""),
                    "source_url": fm.get("source_url", ""),
                    "retrieved_at": fm.get("retrieved_at", ""),
                    "document_version": fm.get("document_version", ""),
                    "audience": fm.get("audience", ""),
                    "category": fm.get("category", ""),
                    "language": fm.get("language", ""),
                },
            )
        )
    return docs


def build_index(docs: list[Document], chunker: HeadingChunker) -> list[IndexedChunk]:
    index: list[IndexedChunk] = []
    for doc in docs:
        chunks = chunker.chunk(doc.content)
        for i, chunk in enumerate(chunks):
            heading = chunk.splitlines()[0] if chunk else ""
            index.append(
                IndexedChunk(
                    chunk_id=f"{doc.id}::chunk_{i}",
                    doc_id=doc.id,
                    heading=heading,
                    content=chunk,
                    metadata={**doc.metadata, "heading": heading},
                    embedding=_mock_embed(chunk),
                )
            )
    return index


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def search(index: list[IndexedChunk], query: str, top_k: int, metadata_filter: dict | None = None) -> list[dict]:
    candidates = index
    if metadata_filter:
        candidates = [
            c for c in index
            if all(c.metadata.get(k) == v for k, v in metadata_filter.items())
        ]
    if not candidates:
        return []
    q_vec = _mock_embed(query)
    scored = [
        {
            "chunk_id": c.chunk_id,
            "doc_id": c.doc_id,
            "heading": c.heading,
            "metadata": c.metadata,
            "content": c.content,
            "score": cosine_similarity(q_vec, c.embedding),
        }
        for c in candidates
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]


# 5 benchmark queries — copied verbatim from 5_CAU_HOI_BENCHMARK (1).md
BENCHMARK = [
    {
        "id": "Q1",
        "query": "Người mua có tối đa bao lâu để gửi yêu cầu trả hàng/hoàn tiền đối với đơn hàng thông thường và thực phẩm tươi sống hoặc đông lạnh?",
        "gold_answer": "Đơn hàng thông thường: 15 ngày kể từ 'Giao hàng thành công'. Thực phẩm tươi sống/đông lạnh: 24 giờ (trừ 'Chưa nhận được hàng').",
        "expected_doc_id": "quy-dinh-chung-tra-hang-hoan-tien",
        "expected_heading_keyword": "1.2.",
        "needs_filter": None,
    },
    {
        "id": "Q2",
        "query": "Trong những trường hợp nào người mua có thể yêu cầu trả hàng/hoàn tiền? Hãy liệt kê ít nhất bốn trường hợp.",
        "gold_answer": "Chưa nhận được hàng; nhận thiếu hàng/phụ kiện/quà; người bán gửi sai hàng; hàng bể vỡ/hư hỏng/rò rỉ; hàng lỗi không hoạt động; khác với mô tả.",
        "expected_doc_id": "quy-dinh-chung-tra-hang-hoan-tien",
        "expected_heading_keyword": "1.3.",
        "needs_filter": None,
    },
    {
        "id": "Q3",
        "query": "Shopee có hỗ trợ đổi sản phẩm trực tiếp không? Người mua nên làm gì nếu sản phẩm nhhận được bị sai hoặc hư hỏng?",
        "gold_answer": "Shopee chưa hỗ trợ yêu cầu đổi hàng. Có thể từ chối nhận khi đồng kiểm, hoặc gửi yêu cầu Trả hàng/Hoàn tiền sau khi nhận hàng.",
        "expected_doc_id": "quy-dinh-chung-tra-hang-hoan-tien",
        "expected_heading_keyword": "1.1.",
        "needs_filter": None,
    },
    {
        "id": "Q4",
        "query": "Sau khi Shopee chấp nhận hoàn tiền, người mua thanh toán khi nhận hàng có thể nhận tiền qua đâu và mất bao lâu?",
        "gold_answer": "Ví ShopeePay trong 24 giờ (nếu ví hoạt động bình thường), hoặc tài khoản ngân hàng mặc định đã liên kết trong 2 ngày làm việc.",
        "expected_doc_id": "thoi-gian-nhan-tien-hoan",
        "expected_heading_keyword": "Thanh toán khi nhận hàng",
        "needs_filter": None,
    },
    {
        "id": "Q5",
        "query": "Khi hệ thống ghi nhận đã trả hàng thành công nhưng Shop chưa nhận được hàng hoặc hàng hoàn gặp vấn đề, người bán phải phản hồi trong thời hạn bao lâu và thực hiện phản hồi ở đâu?",
        "gold_answer": "Trong vòng 2 ngày kể từ ngày hệ thống cập nhật trả hàng thành công. Người bán vào Kênh Quản Lý Shop → Trả hàng/Hoàn tiền → Cần phản hồi → Phản hồi đến Shopee.",
        "expected_doc_id": "quan-ly-don-tra-hang-nguoi-ban",
        "expected_heading_keyword": "C.",
        "needs_filter": {"audience": "seller"},
    },
]


def evaluate(results: list[dict]) -> dict:
    summary = {"total": 0, "top1_hit": 0, "top3_hit": 0, "filter_top1_hit": 0}
    per_query = []
    for r in results:
        summary["total"] += 1
        top_results = r["top_results"]
        top1_doc = top_results[0]["doc_id"] if top_results else None
        top3_docs = [t["doc_id"] for t in top_results]

        top1_hit = top1_doc == r["expected_doc_id"]
        top3_hit = r["expected_doc_id"] in top3_docs
        if top1_hit:
            summary["top1_hit"] += 1
        if top3_hit:
            summary["top3_hit"] += 1

        # Heading keyword check: does top-1 chunk contain the expected heading?
        heading_hit = False
        if top_results:
            heading_hit = r["expected_heading_keyword"].lower() in top_results[0]["heading"].lower()

        # Filter check (Q5 only)
        filter_hit = None
        if r.get("needs_filter") and r.get("filter_top1"):
            filter_hit = r["filter_top1"]["doc_id"] == r["expected_doc_id"]
            if filter_hit:
                summary["filter_top1_hit"] += 1

        per_query.append({
            "id": r["id"],
            "expected_doc_id": r["expected_doc_id"],
            "top1_doc": top1_doc,
            "top1_hit": top1_hit,
            "top3_hit": top3_hit,
            "heading_hit": heading_hit,
            "filter_hit": filter_hit,
        })
    return {"summary": summary, "per_query": per_query}


def main() -> int:
    chunker = HeadingChunker(max_level=3, max_chunk_chars=2000)
    docs = load_documents(DATA_DIR)
    print(f"Loaded {len(docs)} documents from {DATA_DIR}")

    index = build_index(docs, chunker)
    chunk_counts = {doc.id: 0 for doc in docs}
    chunk_lengths: list[int] = []
    for c in index:
        chunk_counts[c.doc_id] += 1
        chunk_lengths.append(len(c.content))
    print(f"Total chunks: {len(index)}")
    print(f"Avg chunk length: {sum(chunk_lengths) / max(len(chunk_lengths), 1):.0f} chars")
    print("Chunks per doc:")
    for doc_id, count in chunk_counts.items():
        print(f"  {doc_id}: {count}")
    print()

    results = []
    for q in BENCHMARK:
        unfiltered = search(index, q["query"], TOP_K)
        entry = {
            "id": q["id"],
            "query": q["query"],
            "expected_doc_id": q["expected_doc_id"],
            "expected_heading_keyword": q["expected_heading_keyword"],
            "needs_filter": q["needs_filter"],
            "top_results": [
                {
                    "doc_id": r["doc_id"],
                    "heading": r["heading"],
                    "score": r["score"],
                    "preview": r["content"][:120].replace("\n", " "),
                }
                for r in unfiltered
            ],
        }
        if q["needs_filter"]:
            entry["filter_top1"] = (
                {
                    "doc_id": unfiltered[0]["doc_id"],
                    "heading": unfiltered[0]["heading"],
                    "score": unfiltered[0]["score"],
                    "preview": unfiltered[0]["content"][:120].replace("\n", " "),
                }
                if unfiltered
                else None
            )
            filtered = search(index, q["query"], TOP_K, metadata_filter=q["needs_filter"])
            entry["filtered_top_results"] = [
                {
                    "doc_id": r["doc_id"],
                    "heading": r["heading"],
                    "score": r["score"],
                    "preview": r["content"][:120].replace("\n", " "),
                }
                for r in filtered
            ]
        results.append(entry)

    evaluation = evaluate(results)

    print("=" * 80)
    print(f"BENCHMARK RESULTS — R3 · HeadingChunker")
    print("=" * 80)
    for r in results:
        print(f"\n[{r['id']}] {r['query'][:80]}...")
        print(f"  expected doc: {r['expected_doc_id']} (heading kw: '{r['expected_heading_keyword']}')")
        for i, hit in enumerate(r["top_results"], 1):
            print(f"  #{i}  score={hit['score']:.3f}  doc={hit['doc_id']}")
            print(f"       heading: {hit['heading']}")
        if "filtered_top_results" in r:
            print("  -- with metadata_filter=", r["needs_filter"], "--")
            for i, hit in enumerate(r["filtered_top_results"], 1):
                print(f"  #{i}  score={hit['score']:.3f}  doc={hit['doc_id']}")
                print(f"       heading: {hit['heading']}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    s = evaluation["summary"]
    print(f"Top-1 hit: {s['top1_hit']}/{s['total']}")
    print(f"Top-3 hit: {s['top3_hit']}/{s['total']}")
    if s.get("filter_top1_hit"):
        print(f"Filter (seller) top-1 hit: {s['filter_top1_hit']}")

    payload = {
        "strategy": "HeadingChunker",
        "chunker_params": {"max_level": chunker.max_level, "max_chunk_chars": chunker.max_chunk_chars},
        "index_stats": {
            "n_docs": len(docs),
            "n_chunks": len(index),
            "avg_chunk_length": sum(chunk_lengths) / max(len(chunk_lengths), 1),
            "chunks_per_doc": chunk_counts,
        },
        "results": results,
        "evaluation": evaluation,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
