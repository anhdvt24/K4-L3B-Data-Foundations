# Giai đoạn 1 — Phân chia code cá nhân (4 người, 4 phần, không overlap)

> **Nguyên tắc:** 4 phần **không overlap**, mỗi người tự chạy test riêng bằng `pytest -k "tên"`. Khi cả 4 xong → chạy `pytest tests/ -v` cả nhóm pass.
>
> **Lưu ý quan trọng:** `FixedSizeChunker` đã được implement sẵn trong `src/chunking.py` (không còn TODO). Vì vậy **không ai phụ trách FixedSizeChunker** — 4 người còn lại chia nhau 7 TODO còn lại.
>
> **Quy ước:**
> - Tất cả sửa file `src/chunking.py`, `src/store.py`, `src/agent.py` (file khác **không động vào**).
> - Mỗi người tự chạy test phần mình trước khi merge.
> - Tất cả hàm đều là method/class thuần Python; **không cần** API key, **không cần** chờ thành viên khác.

---

## 📦 Phần 1 — Người 1: `SentenceChunker` + `compute_similarity`

**File sửa:** `src/chunking.py`

### TODO 1.1 — `SentenceChunker.chunk(text)`

```python
def chunk(self, text: str) -> list[str]:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- Tách `text` thành các câu theo ranh giới `". "`, `"! "`, `"? "`, hoặc `".\n"`.
- Gom nhóm các câu liên tiếp thành chunk sao cho **mỗi chunk ≤ `max_sentences_per_chunk` câu**.
- Mỗi chunk là chuỗi `str`, đã strip whitespace thừa ở đầu/cuối.
- Nếu `text` rỗng → trả `[]`.
- `max_sentences_per_chunk` đã được clamp về ≥ 1 trong `__init__`.

**Cách tách câu gợi ý:**
```python
import re
SENT_END = re.compile(r'(?<=[.!?])\s+')  # hoặc split trên các chuỗi ". ", "! ", "? "
parts = SENT_END.split(text.strip())
```

### TODO 1.2 — `compute_similarity(vec_a, vec_b)`

```python
def compute_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- Trả về `dot(a, b) / (||a|| * ||b||)`.
- Nếu một trong hai vector có norm = 0 → trả `0.0`.
- Có thể dùng helper `_dot(a, b)` đã có sẵn trong file.

### Acceptance — chạy test

```bash
pytest tests/ -v -k "SentenceChunker or ComputeSimilarity"
```

Kỳ vọng: **tất cả pass** (khoảng 8 test, gồm 4 test SentenceChunker + 4 test ComputeSimilarity).

### Lưu ý

- KHÔNG sửa `FixedSizeChunker` (đã có sẵn).
- KHÔNG đụng vào các hàm/class khác trong `src/chunking.py`.
- Code phải pass `mypy` hoặc `pyright` cơ bản (không có lỗi type rõ ràng).

---

## 📦 Phần 2 — Người 2: `RecursiveChunker`

**File sửa:** `src/chunking.py`

### TODO 2.1 — `RecursiveChunker.chunk(text)`

```python
def chunk(self, text: str) -> list[str]:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- Entry point: `return self._split(text, list(self.separators))`.

### TODO 2.2 — `RecursiveChunker._split(current_text, remaining_separators)`

```python
def _split(self, current_text: str, remaining_separators: list[str]) -> list[str]:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu (thuật toán đệ quy):**
1. **Base case:** nếu `len(current_text) ≤ self.chunk_size` → trả `[current_text]`.
2. Nếu `remaining_separators` rỗng → cắt cứng `current_text` thành các đoạn ≤ `chunk_size`, trả về list.
3. Lấy `sep = remaining_separators[0]`, các sep còn lại = `remaining_separators[1:]`.
4. Nếu `sep` không xuất hiện trong `current_text` (hoặc `sep == ""`) → gọi đệ quy `_split(current_text, các_sep_còn_lại)`.
5. Nếu `sep` có trong text → tách `current_text` theo `sep` thành list `pieces`. Với mỗi piece:
   - Ghép sep vào cuối piece (trừ piece cuối cùng) để giữ ranh giới.
   - Nếu `len(piece_with_sep) ≤ chunk_size` → đưa vào buffer chunk hiện tại; nếu thêm vào vượt `chunk_size` → đóng chunk cũ, mở chunk mới.
   - Nếu `len(piece_with_sep) > chunk_size` → đóng buffer, rồi gọi đệ quy `_split(piece, các_sep_còn_lại)` để tách nhỏ hơn.
6. Trả về list các chunks (đã strip 2 đầu).

**Sep mặc định:** `["\n\n", "\n", ". ", " ", ""]` (đã có trong `DEFAULT_SEPARATORS`).

### Acceptance — chạy test

```bash
pytest tests/ -v -k "RecursiveChunker"
```

Kỳ vọng: **4 test pass**:
- `test_returns_list`
- `test_chunks_within_size_when_possible` (≥80% chunks ≤ chunk_size + 10)
- `test_empty_separators_falls_back_gracefully` (không crash khi `separators=[]`)
- `test_handles_double_newline_separator`

### Lưu ý

- KHÔNG đụng `SentenceChunker` hay `compute_similarity` của Người 1.
- Có thể dùng helper `_dot` đã có sẵn (không bắt buộc).
- Nếu dùng regex cho separator, hãy để `re.escape(sep)` tránh lỗi với sep đặc biệt.

---

## 📦 Phần 3 — Người 3 (BẠN): `EmbeddingStore` (cả 5 method)

**File sửa:** `src/store.py`

### TODO 3.1 — `_make_record(doc)`

```python
def _make_record(self, doc: Document) -> dict[str, Any]:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:** Trả dict dạng:
```python
{
    "id": doc.id,
    "content": doc.content,
    "metadata": dict(doc.metadata),   # copy để tránh mutate
    "embedding": self._embedding_fn(doc.content),
}
```

### TODO 3.2 — `_search_records(query, records, top_k)`

```python
def _search_records(self, query: str, records: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- Embed query bằng `self._embedding_fn(query)`.
- Tính cosine-sim giữa query và từng record's embedding (dùng `compute_similarity` từ `src.chunking`).
- Trả top_k record theo score giảm dần, **kèm key `score`**.
- Nếu list rỗng → trả `[]`.

### TODO 3.3 — `add_documents(docs)`

```python
def add_documents(self, docs: list[Document]) -> None:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- Với mỗi `doc` trong `docs`: gọi `_make_record(doc)`, append vào `self._store`.
- Tăng `self._next_index` cho mỗi record (nếu muốn, không bắt buộc cho test).

### TODO 3.4 — `search(query, top_k=5)`

```python
def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:** Gọi `_search_records(query, list(self._store), top_k)`.

### TODO 3.5 — `get_collection_size()`

```python
def get_collection_size(self) -> int:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:** Trả `len(self._store)`.

### TODO 3.6 — `search_with_filter(query, top_k, metadata_filter)`

```python
def search_with_filter(self, query: str, top_k: int = 3, metadata_filter: dict = None) -> list[dict]:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- Nếu `metadata_filter` là None/{} → trả `self.search(query, top_k)`.
- Ngược lại: lọc `self._store` giữ lại các record có `metadata` chứa tất cả key=value trong filter (so sánh `==`).
- Gọi `_search_records(query, filtered, top_k)`.

### TODO 3.7 — `delete_document(doc_id)`

```python
def delete_document(self, doc_id: str) -> bool:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- Lọc `self._store` giữ lại các record có `metadata.get("doc_id") != doc_id`.
- Trả `True` nếu có record bị xoá, `False` nếu không.
- Hỗ trợ cả `record["id"] == doc_id` (fallback).

**Lưu ý:** Test `setUp` của `TestEmbeddingStoreDeleteDocument` tạo doc với `metadata={}`, không có key `"doc_id"`. Vì vậy cần check cả `record["id"]` để test pass:

```python
def delete_document(self, doc_id: str) -> bool:
    before = len(self._store)
    self._store = [
        r for r in self._store
        if r.get("id") != doc_id and r.get("metadata", {}).get("doc_id") != doc_id
    ]
    return len(self._store) < before
```

### Acceptance — chạy test

```bash
pytest tests/ -v -k "EmbeddingStore"
```

Kỳ vọng: **14 test pass** (8 của `TestEmbeddingStore` + 3 của `TestEmbeddingStoreSearchWithFilter` + 3 của `TestEmbeddingStoreDeleteDocument`).

### Lưu ý

- KHÔNG sửa `src/chunking.py` (phần của Người 1, 2).
- KHÔNG sửa `src/agent.py` (phần của Người 4).
- File này đang dùng `_dot` và `_mock_embed` — giữ nguyên import.
- Có thể import `compute_similarity` từ `src.chunking`.

---

## 📦 Phần 4 — Người 4: `KnowledgeBaseAgent` + `ChunkingStrategyComparator`

**File sửa:** `src/agent.py` + `src/chunking.py`

### TODO 4.1 — `KnowledgeBaseAgent.__init__(store, llm_fn)`

```python
def __init__(self, store: EmbeddingStore, llm_fn: Callable[[str], str]) -> None:
    # Hiện tại: pass
```

**Yêu cầu:**
- `self.store = store`
- `self.llm_fn = llm_fn`

### TODO 4.2 — `KnowledgeBaseAgent.answer(question, top_k=3)`

```python
def answer(self, question: str, top_k: int = 3) -> str:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- `chunks = self.store.search(question, top_k=top_k)` → mỗi chunk có key `"content"` và `"score"`.
- Build prompt kiểu:
  ```
  Use the following context to answer the question.

  Context:
  - <chunk_1_content>
  - <chunk_2_content>
  - <chunk_3_content>

  Question: <question>
  Answer:
  ```
- Trả `self.llm_fn(prompt)`.

### TODO 4.3 — `ChunkingStrategyComparator.compare(text, chunk_size=200)`

```python
def compare(self, text: str, chunk_size: int = 200) -> dict:
    # Hiện tại: raise NotImplementedError(...)
```

**Yêu cầu:**
- Chạy 3 chunker trên `text`:
  - `FixedSizeChunker(chunk_size=chunk_size, overlap=50)`
  - `SentenceChunker(max_sentences_per_chunk=3)`
  - `RecursiveChunker(chunk_size=chunk_size)`
- Với mỗi chunker, tính stats:
  - `count`: số chunks.
  - `avg_length`: trung bình `len(chunk)`.
  - `chunks`: list các chunk thực (không strip — giữ nguyên để xem).
- Trả dict dạng:
  ```python
  {
      "fixed_size": {"count": ..., "avg_length": ..., "chunks": [...]},
      "by_sentences": {"count": ..., "avg_length": ..., "chunks": [...]},
      "recursive": {"count": ..., "avg_length": ..., "chunks": [...]},
  }
  ```

### Acceptance — chạy test

```bash
pytest tests/ -v -k "KnowledgeBaseAgent or CompareChunking"
```

Kỳ vọng: **5 test pass** (2 của `TestKnowledgeBaseAgent` + 3 của `TestCompareChunkingStrategies`).

### Lưu ý

- KHÔNG sửa `src/store.py` (phần của Người 3).
- `compare()` cần `SentenceChunker` (Người 1) và `RecursiveChunker` (Người 2) — nếu chưa có, test sẽ fail vì raise NotImplementedError; **mỗi người tự chạy test của mình trước, cuối cùng cả nhóm chạy chung**.

---

## ✅ Khi cả 4 xong — chạy toàn bộ

```bash
pytest tests/ -v
```

Kỳ vọng: **tất cả test pass** (~30 test). Đây là **điểm 30 "Hoàn thiện code"** trong `REPORT_CANHAN.md`.

---

## 📋 Tóm tắt

| Phần | Người | File sửa | Hàm/Class | Test |
|------|-------|----------|-----------|------|
| 1 | Người 1 | `src/chunking.py` | `SentenceChunker.chunk`, `compute_similarity` | `pytest -k "SentenceChunker or ComputeSimilarity"` |
| 2 | Người 2 | `src/chunking.py` | `RecursiveChunker.chunk`, `_split` | `pytest -k "RecursiveChunker"` |
| 3 | Người 3 (BẠN) | `src/store.py` | `EmbeddingStore` × 7 method (gồm `_make_record`, `_search_records`, `add_documents`, `search`, `get_collection_size`, `search_with_filter`, `delete_document`) | `pytest -k "EmbeddingStore"` |
| 4 | Người 4 | `src/agent.py`, `src/chunking.py` | `KnowledgeBaseAgent` × 2, `ChunkingStrategyComparator.compare` | `pytest -k "KnowledgeBaseAgent or CompareChunking"` |
| — | (không ai) | — | `FixedSizeChunker` — **đã có sẵn code đầy đủ** | `TestFixedSizeChunker` đã pass |

**Mỗi người tự chạy test của mình trước khi merge. Cuối cùng cả nhóm chạy `pytest tests/ -v`.**
