"""Filter ablation: đo tác động của metadata_filter lên retrieval quality.

Câu hỏi trọng tâm: `metadata_filter` thực sự cải thiện bao nhiêu điểm?
Đây là bằng chứng thực nghiệm (proof-of-impact) mà rubric SCORING.md yêu cầu.

Pipeline: load 10 file .md -> HeadingChunker -> MockEmbedder -> 5 query
Hai chế độ: search() vs search_with_filter(metadata_filter={"audience": "seller"}).
Đánh giá theo SCORING.md: 2đ nếu top-3 chứa gold-doc + context_has_answer, 1đ nếu top-3 chứa gold nhưng
không ở top-1, 0đ nếu không có gold trong top-3.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Allow running this script directly without installing the package.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.chunking import HeadingChunker
from src.embeddings import _mock_embed
from src.models import Document
from src.store import EmbeddingStore


DATA_DIR = PROJECT_ROOT / "data" / "ecommerce"


def load_documents(data_dir: Path) -> list[Document]:
    """Load all .md files in data_dir, parsing YAML front matter into metadata."""
    docs: list[Document] = []
    for md_path in sorted(data_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            docs.append(Document(id=md_path.stem, content=text, metadata={}))
            continue
        # Find closing `---` line (allowing `---` to be at end of a content line
        # such as `language: vi---` as well as on its own line).
        lines = text.splitlines(keepends=True)
        end_line_idx = None
        for i in range(1, len(lines)):
            line = lines[i].rstrip("\n").rstrip("\r")
            if line == "---" or line.endswith("---"):
                end_line_idx = i
                break
        if end_line_idx is None:
            docs.append(Document(id=md_path.stem, content=text, metadata={}))
            continue
        front_matter = "".join(lines[1:end_line_idx]).strip()
        body = "".join(lines[end_line_idx + 1 :]).lstrip("\n")
        metadata: dict[str, str] = {}
        for raw_line in front_matter.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()
        docs.append(Document(id=md_path.stem, content=body, metadata=metadata))
    return docs


# Same 5 benchmark queries used by the team.
BENCHMARK: list[dict[str, str]] = [
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


def score_top_k(top_docs: list[str], gold_doc: str) -> int:
    """Score 2 if gold-doc in top-1, 1 if in top-3, else 0.

    Note: SCORING.md requires top-3 + context_has_answer. With MockEmbedder
    context_has_answer is approximated by gold_doc presence in top-3.
    """
    if not top_docs:
        return 0
    if top_docs[0] == gold_doc:
        return 2
    if gold_doc in top_docs[:3]:
        return 1
    return 0


def run_ablation() -> dict:
    docs = load_documents(DATA_DIR)
    chunker = HeadingChunker(max_level=3, max_chunk_chars=2000)

    # Split each document into chunks; emit a Document per chunk preserving metadata.
    chunk_docs: list[Document] = []
    chunk_index: dict[str, list[str]] = {}
    for doc in docs:
        chunks = chunker.chunk(doc.content)
        chunk_index[doc.id] = chunks
        for idx, chunk in enumerate(chunks):
            chunk_docs.append(
                Document(
                    id=f"{doc.id}#{idx}",
                    content=chunk,
                    metadata={**doc.metadata, "parent_doc_id": doc.id},
                )
            )

    store = EmbeddingStore(embedding_fn=_mock_embed)
    store.add_documents(chunk_docs)
    print(f"Loaded {len(docs)} docs -> {len(chunk_docs)} chunks")
    print(f"Chunk count by file: {[(doc_id, len(c)) for doc_id, c in chunk_index.items()]}")

    results = {
        "strategy": "HeadingChunker",
        "embedding": "MockEmbedder",
        "n_docs": len(docs),
        "n_chunks": len(chunk_docs),
        "queries": [],
        "summary": {
            "no_filter": {"total_points": 0, "per_query": {}},
            "with_filter": {"total_points": 0, "per_query": {}},
        },
    }

    no_filter_total = 0
    with_filter_total = 0

    for q in BENCHMARK:
        qid = q["id"]
        gold = q["gold_doc"]
        needs_filter = q["needs_filter"]

        # Variant A: no filter
        top_nf = store.search(q["query"], top_k=3)
        nf_docs = [r["id"].split("#")[0] for r in top_nf]
        nf_score = score_top_k(nf_docs, gold)
        no_filter_total += nf_score

        # Variant B: with filter (only for Q5)
        wf_score = None
        wf_docs = None
        if needs_filter:
            top_wf = store.search_with_filter(q["query"], top_k=3, metadata_filter=needs_filter)
            wf_docs = [r["id"].split("#")[0] for r in top_wf]
            wf_score = score_top_k(wf_docs, gold)
            with_filter_total += wf_score

        results["queries"].append(
            {
                "id": qid,
                "gold_doc": gold,
                "needs_filter": needs_filter,
                "no_filter": {"top3": nf_docs, "score": nf_score},
                "with_filter": (
                    {"top3": wf_docs, "score": wf_score, "filter": needs_filter}
                    if wf_score is not None
                    else None
                ),
            }
        )
        results["summary"]["no_filter"]["per_query"][qid] = nf_score
        if wf_score is not None:
            results["summary"]["with_filter"]["per_query"][qid] = wf_score

        filter_part = f"  filter={wf_docs} score={wf_score}" if wf_docs is not None else ""
        print(f"[{qid}] no_filter={nf_docs} score={nf_score}{filter_part}")

    results["summary"]["no_filter"]["total_points"] = no_filter_total
    results["summary"]["no_filter"]["max_points"] = 10
    results["summary"]["with_filter"]["total_points"] = with_filter_total
    results["summary"]["with_filter"]["max_points"] = 2  # only Q5 has filter

    print()
    print("=" * 60)
    print(f"TOTAL (no filter, 5 queries) : {no_filter_total}/10")
    print(f"TOTAL (with filter Q5 only)   : {no_filter_total}/10 (Q5 = {with_filter_total}/2)")
    print(f"=> Filter only helps Q5, improves {with_filter_total} points")
    print("=" * 60)

    return results


def main() -> None:
    out_path = PROJECT_ROOT / "data" / "filter_ablation.json"
    results = run_ablation()
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
