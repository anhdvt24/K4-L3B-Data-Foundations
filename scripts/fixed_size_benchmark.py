"""
Benchmark G00 với FixedSizeChunker(chunk_size=500, overlap=80) + MockEmbedder.

Mục tiêu: so sánh công bằng với kết quả SentenceChunker(max=3) của Thái Anh
(vì cùng embedder). Xuất data/fixed_size_benchmark.json + in summary.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent import KnowledgeBaseAgent
from src.chunking import FixedSizeChunker
from src.embeddings import _mock_embed
from src.models import Document
from src.store import EmbeddingStore


DATA_DIR = Path("data/ecommerce")
TOP_K = 3


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
    docs = []
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
                    "doc_id": fm.get("doc_id", p.stem),
                },
            )
        )
    return docs


def demo_llm(prompt: str) -> str:
    if "Context:" in prompt:
        ctx = prompt.split("Context:", 1)[1].split("Question:", 1)[0].strip()
        lines = [ln.strip() for ln in ctx.splitlines() if ln.strip() and ln.strip() != "-"]
        snippet = " ".join(lines[:3])[:280]
        return f"[MOCK LLM] Dựa trên ngữ cảnh truy xuất được: {snippet}..."
    return "[MOCK LLM] Không có context để trả lời."


BENCHMARK = [
    {
        "id": "Q1",
        "query": "Người mua có tối đa bao lâu để gửi yêu cầu trả hàng/hoàn tiền đối với đơn hàng thông thường và thực phẩm tươi sống hoặc đông lạnh?",
        "gold_doc": "quy-dinh-chung-tra-hang-hoan-tien",
        "needs_filter": None,
    },
    {
        "id": "Q2",
        "query": "Trong những trường hợp nào người mua có thể yêu cầu trả hàng/hoàn tiền? Hãy liệt kê ít nhất bốn trường hợp.",
        "gold_doc": "quy-dinh-chung-tra-hang-hoan-tien",
        "needs_filter": None,
    },
    {
        "id": "Q3",
        "query": "Shopee có hỗ trợ đổi sản phẩm trực tiếp không? Người mua nên làm gì nếu sản phẩm nhận được bị sai hoặc hư hỏng?",
        "gold_doc": "quy-dinh-chung-tra-hang-hoan-tien",
        "needs_filter": None,
    },
    {
        "id": "Q4",
        "query": "Sau khi Shopee chấp nhận hoàn tiền, người mua thanh toán khi nhận hàng có thể nhận tiền qua đâu và mất bao lâu?",
        "gold_doc": "thoi-gian-nhan-tien-hoan",
        "needs_filter": None,
    },
    {
        "id": "Q5",
        "query": "Khi hệ thống ghi nhận đã trả hàng thành công nhưng Shop chưa nhận được hàng hoặc hàng hoàn gặp vấn đề, người bán phải phản hồi trong thời hạn bao lâu và thực hiện phản hồi ở đâu?",
        "gold_doc": "quan-ly-don-tra-hang-nguoi-ban",
        "needs_filter": {"audience": "seller"},
    },
]


def main() -> int:
    print("=" * 80)
    print("BENCHMARK NHÓM G00 — FixedSizeChunker(chunk_size=500, overlap=80)")
    print("Embedding: MockEmbedder 64-dim (deterministic hash)")
    print("=" * 80)

    chunker = FixedSizeChunker(chunk_size=500, overlap=80)
    docs = load_documents(DATA_DIR)
    print(f"\nLoaded {len(docs)} documents from {DATA_DIR}")

    chunk_records = []
    for doc in docs:
        for i, chunk in enumerate(chunker.chunk(doc.content)):
            chunk_records.append(
                Document(
                    id=f"{doc.id}::chunk_{i}",
                    content=chunk,
                    metadata={**doc.metadata, "doc_id": doc.id},
                )
            )
    print(f"Total chunks: {len(chunk_records)}")
    print(f"Chunks per file:")
    per_file = {}
    for rec in chunk_records:
        per_file[rec.metadata["doc_id"]] = per_file.get(rec.metadata["doc_id"], 0) + 1
    for fn, cnt in sorted(per_file.items()):
        print(f"  - {fn:40s} : {cnt:3d}")

    store = EmbeddingStore(collection_name="fixed_size_r3", embedding_fn=_mock_embed)
    store.add_documents(chunk_records)
    print(f"EmbeddingStore size: {store.get_collection_size()}")

    agent = KnowledgeBaseAgent(store=store, llm_fn=demo_llm)

    summary = {"top1_hit": 0, "top3_hit": 0, "filter_top1_hit": 0, "total": 0}
    results = []

    for q in BENCHMARK:
        top = store.search(q["query"], top_k=TOP_K)
        top1_doc = top[0]["metadata"]["doc_id"] if top else None
        top3_docs = [r["metadata"]["doc_id"] for r in top]
        top1_hit = top1_doc == q["gold_doc"]
        top3_hit = q["gold_doc"] in top3_docs

        filter_top1_doc = None
        filter_top1_hit = None
        if q["needs_filter"]:
            ftop = store.search_with_filter(
                q["query"], top_k=TOP_K, metadata_filter=q["needs_filter"]
            )
            filter_top1_doc = ftop[0]["metadata"]["doc_id"] if ftop else None
            filter_top1_hit = filter_top1_doc == q["gold_doc"]

        answer = agent.answer(q["query"], top_k=TOP_K)

        summary["total"] += 1
        if top1_hit:
            summary["top1_hit"] += 1
        if top3_hit:
            summary["top3_hit"] += 1
        if filter_top1_hit:
            summary["filter_top1_hit"] += 1

        print(f"\n{'─' * 80}")
        print(f"[{q['id']}] {q['query']}")
        print(f"  Gold doc : {q['gold_doc']}")
        for i, r in enumerate(top, 1):
            snippet = r["content"][:120].replace("\n", " ")
            print(f"  #{i}  score={r['score']:+.4f}  doc={r['metadata']['doc_id']}")
            print(f"       preview: {snippet}…")
        if q["needs_filter"]:
            ftop = store.search_with_filter(
                q["query"], top_k=TOP_K, metadata_filter=q["needs_filter"]
            )
            print(f"  -- with metadata_filter={q['needs_filter']} --")
            for i, r in enumerate(ftop, 1):
                snippet = r["content"][:120].replace("\n", " ")
                print(f"  #{i}  score={r['score']:+.4f}  doc={r['metadata']['doc_id']}")
                print(f"       preview: {snippet}…")
        print(f"\n  Agent answer: {answer[:300]}{'...' if len(answer) > 300 else ''}")
        print(
            f"  → top1_hit={top1_hit}  top3_hit={top3_hit}  filter_hit={filter_top1_hit}"
        )

        results.append({
            "id": q["id"],
            "query": q["query"],
            "gold_doc": q["gold_doc"],
            "top1_doc": top1_doc,
            "top3_docs": top3_docs,
            "top1_hit": top1_hit,
            "top3_hit": top3_hit,
            "filter_top1_doc": filter_top1_doc,
            "filter_top1_hit": filter_top1_hit,
            "agent_answer": answer,
            "top_chunks": [
                {"doc": r["metadata"]["doc_id"], "score": r["score"], "preview": r["content"][:200]}
                for r in top
            ],
        })

    print("\n" + "=" * 80)
    print("TÓM TẮT (FixedSizeChunker 500/80, MockEmbedder)")
    print("=" * 80)
    print(f"Top-1 hit (no filter) : {summary['top1_hit']}/{summary['total']}")
    print(f"Top-3 hit (no filter) : {summary['top3_hit']}/{summary['total']}")
    print(f"Filter top-1 hit (Q5) : {summary['filter_top1_hit']}/1")

    # Tính điểm theo rubric docs/SCORING.md (2 điểm/câu)
    rubric_points = {
        "Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0, "Q5": 0,
    }
    for r in results:
        # Q5 chỉ có filter → nếu filter đúng → 2 điểm
        if r["id"] == "Q5":
            if r["filter_top1_hit"]:
                rubric_points["Q5"] = 2
            elif r["top3_hit"]:
                rubric_points["Q5"] = 1
        else:
            if r["top1_hit"]:
                rubric_points["Q1"] = 2 if r["id"] == "Q1" else rubric_points["Q1"]
                if r["id"] == "Q1":
                    rubric_points["Q1"] = 2
                elif r["id"] == "Q2":
                    rubric_points["Q2"] = 2
                elif r["id"] == "Q3":
                    rubric_points["Q3"] = 2
                elif r["id"] == "Q4":
                    rubric_points["Q4"] = 2
            elif r["top3_hit"]:
                if r["id"] == "Q1":
                    rubric_points["Q1"] = 1
                elif r["id"] == "Q2":
                    rubric_points["Q2"] = 1
                elif r["id"] == "Q3":
                    rubric_points["Q3"] = 1
                elif r["id"] == "Q4":
                    rubric_points["Q4"] = 1
    total_pts = sum(rubric_points.values())
    print(f"\nĐiểm theo rubric SCORING.md (2đ/câu):")
    for k, v in rubric_points.items():
        print(f"  {k}: {v}/2")
    print(f"  Tổng: {total_pts}/10")

    out_path = Path("data/fixed_size_benchmark.json")
    out_path.write_text(
        json.dumps(
            {"owner": "Đặng Văn Thái Anh (chạy thêm FixedSize)",
             "strategy": "FixedSizeChunker(chunk_size=500, overlap=80)",
             "embedding": "MockEmbedder 64-dim",
             "summary": summary,
             "rubric_points": rubric_points,
             "total_points": total_pts,
             "max_points": 10,
             "results": results},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nFull JSON saved to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())