"""Heading-injection ablation: chứng minh rằng tiêm heading vào chunk Sentence
cải thiện retrieval cho các câu hỏi phủ định (negation, Q3) và phụ thuộc vào
mục chính sách (Q1, Q4).

Ý tưởng: sau khi `SentenceChunker.chunk(text)` sinh ra các chunk "thuần câu",
ta tìm heading Markdown gần nhất phía trên trong document gốc và ghép vào
đầu chunk. Đây là post-processing rẻ và không phụ thuộc LLM.

So sánh hai pipeline trên cùng corpus, cùng MockEmbedder, cùng 5 query:
  A) SentenceChunker(max=3) thuần
  B) SentenceChunker(max=3) + heading injection

Tiêu chí đo:
  - top-3 hit (gold-doc có trong top-3 không)
  - Điểm SCORING.md (2/1/0 theo vị trí gold)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.chunking import HeadingChunker, SentenceChunker
from src.embeddings import _mock_embed
from src.models import Document
from src.store import EmbeddingStore


DATA_DIR = PROJECT_ROOT / "data" / "ecommerce"

# Same 5 benchmark queries (must stay in sync with filter_ablation.py).
BENCHMARK: list[dict[str, str]] = [
    {"id": "Q1", "gold_doc": "quy-dinh-chung-tra-hang-hoan-tien"},
    {"id": "Q2", "gold_doc": "quy-dinh-chung-tra-hang-hoan-tien"},
    {"id": "Q3", "gold_doc": "quy-dinh-chung-tra-hang-hoan-tien"},
    {"id": "Q4", "gold_doc": "thoi-gian-nhan-tien-hoan"},
    {"id": "Q5", "gold_doc": "quan-ly-don-tra-hang-nguoi-ban"},
]

QUERIES: dict[str, str] = {
    "Q1": "Người mua có tối đa bao lâu để gửi yêu cầu trả hàng/hoàn tiền đối với đơn hàng thông thường và thực phẩm tươi sống hoặc đông lạnh?",
    "Q2": "Trong những trường hợp nào người mua có thể yêu cầu trả hàng/hoàn tiền? Hãy liệt kê ít nhất bốn trường hợp.",
    "Q3": "Shopee có hỗ trợ đổi sản phẩm trực tiếp không? Người mua nên làm gì nếu sản phẩm nhận được bị sai hoặc hư hỏng?",
    "Q4": "Sau khi Shopee chấp nhận hoàn tiền, người mua thanh toán khi nhận hàng có thể nhận tiền qua đâu và mất bao lâu?",
    "Q5": "Khi hệ thống ghi nhận đã trả hàng thành công nhưng Shop chưa nhận được hàng hoặc hàng hoàn gặp vấn đề, người bán phải phản hồi trong thời hạn bao lâu và thực hiện phản hồi ở đâu?",
}


def load_documents(data_dir: Path) -> list[Document]:
    docs: list[Document] = []
    for md_path in sorted(data_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            docs.append(Document(id=md_path.stem, content=text, metadata={}))
            continue
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


HEADING_RE = re.compile(
    r"^(?P<hash>#{1,6})\s+(?P<title_hash>.+?)\s*#*\s*$"
    r"|^(?P<num>\d+(?:\.\d+)*\.)\s+(?P<title_num>\S.*?)\s*$"
    r"|^(?P<letter>[A-Z]\.)\s+(?P<title_letter>\S.*?)\s*$"
)


def find_nearest_heading(text: str, char_offset: int) -> str:
    """Return the most recent heading line ending at or before `char_offset`,
    or empty string if none found."""
    prefix = text[:char_offset]
    headings = []
    for line in prefix.splitlines():
        if HEADING_RE.match(line.strip()):
            headings.append(line.strip())
    return headings[-1] if headings else ""


def chunk_with_heading_injection(text: str, max_sentences: int = 3) -> list[str]:
    """SentenceChunker + heading injection: ghép heading gần nhất vào đầu mỗi chunk."""
    sentence_chunker = SentenceChunker(max_sentences_per_chunk=max_sentences)
    base_chunks = sentence_chunker.chunk(text)
    if not base_chunks:
        return []

    # Map each chunk back to its position in the original text.
    enriched: list[str] = []
    cursor = 0
    for chunk in base_chunks:
        # Locate the chunk in the source text starting from `cursor`.
        idx = text.find(chunk, cursor)
        if idx == -1:
            # Fallback: try fuzzy match (chunk may have been normalized)
            idx = text.find(chunk.split(".")[0], cursor)
            if idx == -1:
                enriched.append(chunk)
                cursor += len(chunk)
                continue
        heading = find_nearest_heading(text, idx)
        if heading:
            enriched.append(f"{heading}\n{chunk}")
        else:
            enriched.append(chunk)
        cursor = idx + len(chunk)
    return enriched


def score_top_k(top_docs: list[str], gold_doc: str) -> int:
    if not top_docs:
        return 0
    if top_docs[0] == gold_doc:
        return 2
    if gold_doc in top_docs[:3]:
        return 1
    return 0


def run_ablation() -> dict:
    docs = load_documents(DATA_DIR)

    # Build two stores: SentenceChunker thuần vs SentenceChunker + heading injection.
    stores = {}
    chunk_counts = {}

    for variant, chunker_fn in [
        ("sentence", lambda text: SentenceChunker(max_sentences_per_chunk=3).chunk(text)),
        ("sentence_with_heading", lambda text: chunk_with_heading_injection(text, max_sentences=3)),
    ]:
        chunk_docs: list[Document] = []
        for doc in docs:
            chunks = chunker_fn(doc.content)
            for idx, chunk in enumerate(chunks):
                chunk_docs.append(
                    Document(
                        id=f"{doc.id}#{idx}",
                        content=chunk,
                        metadata={**doc.metadata, "parent_doc_id": doc.id},
                    )
                )
        chunk_counts[variant] = len(chunk_docs)
        store = EmbeddingStore(embedding_fn=_mock_embed)
        store.add_documents(chunk_docs)
        stores[variant] = store
        print(f"[{variant}] chunks={len(chunk_docs)}")

    results: dict = {
        "strategy_A": "SentenceChunker(max=3)",
        "strategy_B": "SentenceChunker(max=3) + heading injection",
        "embedding": "MockEmbedder",
        "chunks": chunk_counts,
        "queries": [],
        "summary": {"A": 0, "B": 0},
    }

    total_a = 0
    total_b = 0

    for q in BENCHMARK:
        qid = q["id"]
        gold = q["gold_doc"]
        query = QUERIES[qid]

        top_a = stores["sentence"].search(query, top_k=3)
        top_a_docs = [r["id"].split("#")[0] for r in top_a]
        score_a = score_top_k(top_a_docs, gold)
        total_a += score_a

        top_b = stores["sentence_with_heading"].search(query, top_k=3)
        top_b_docs = [r["id"].split("#")[0] for r in top_b]
        score_b = score_top_k(top_b_docs, gold)
        total_b += score_b

        delta = score_b - score_a
        results["queries"].append(
            {
                "id": qid,
                "gold_doc": gold,
                "A": {"top3": top_a_docs, "score": score_a},
                "B": {"top3": top_b_docs, "score": score_b},
                "delta": delta,
            }
        )
        marker = "+" if delta > 0 else ("=" if delta == 0 else "-")
        print(f"[{qid}] A={top_a_docs[:3]} ({score_a}) | B={top_b_docs[:3]} ({score_b}) | delta={delta:+d} {marker}")

    results["summary"]["A"] = total_a
    results["summary"]["B"] = total_b
    results["summary"]["delta"] = total_b - total_a

    print()
    print("=" * 60)
    print(f"TOTAL A (sentence only)             : {total_a}/10")
    print(f"TOTAL B (sentence + heading injection): {total_b}/10")
    print(f"Delta                               : {total_b - total_a:+d}")
    print("=" * 60)

    return results


def main() -> None:
    out_path = PROJECT_ROOT / "data" / "heading_injection_ablation.json"
    results = run_ablation()
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
