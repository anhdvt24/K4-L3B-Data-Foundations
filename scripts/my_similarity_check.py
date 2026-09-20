"""
Bằng chứng thực nghiệm cho REPORT_CANHAN.md — Mục 4 (Similarity Predictions).

Chạy `compute_similarity()` thực sự trên 5 cặp câu từ corpus Shopee
(bằng MockEmbedder 64-dim, hash deterministic) và in kết quả chi tiết
ra stdout để paste vào báo cáo.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Force UTF-8 on stdout/stderr for Windows Vietnamese text
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chunking import compute_similarity
from src.embeddings import _mock_embed

# 5 cặp câu được thiết kế theo 3 nhóm:
# - Cặp 1, 2: ngữ nghĩa GIỐNG nhau (kỳ vọng cosine CAO).
# - Cặp 3, 4: ngữ nghĩa KHÁC nhau (kỳ vọng cosine THẤP).
# - Cặp 5: chung từ khoá "trả hàng" nhưng khác ý nghĩa (test sự "ngạc nhiên").

PAIRS = [
    (
        "Sản phẩm nhận được bị lỗi, tôi muốn trả hàng hoàn tiền.",
        "Hàng bể vỡ, hư hỏng có được trả không?",
    ),
    (
        "Thời gian nhận tiền hoàn khi thanh toán khi nhận hàng là bao lâu?",
        "Cách kiểm tra tiền hoàn vào tài khoản ngân hàng?",
    ),
    (
        "Shopee có hỗ trợ đổi sản phẩm không?",
        "Phí hoàn trả do ai chịu?",
    ),
    (
        "Người bán phản hồi trên Kênh Quản Lý Shop ở đâu?",
        "Hướng dẫn đăng ký bán hàng trên Shopee.",
    ),
    (
        "Quy trình Shopee xử lý yêu cầu trả hàng hoàn tiền.",
        "Sản phẩm hạn chế trả hàng là gì?",
    ),
]

print("=" * 80)
print("BẰNG CHỨNG THỰC NGHIỆM — Mục 4: Dự đoán độ tương tự Cosine")
print("Backend: MockEmbedder 64-dim (hash deterministic, normalize=True)")
print("=" * 80)

scores = []
for i, (a, b) in enumerate(PAIRS, 1):
    va = _mock_embed(a)
    vb = _mock_embed(b)
    s = compute_similarity(va, vb)
    scores.append(s)
    print(f"\n[Cặp {i}]")
    print(f"  A: {a}")
    print(f"  B: {b}")
    print(f"  ||A|| = {sum(x*x for x in va) ** 0.5:.4f}")
    print(f"  ||B|| = {sum(x*x for x in vb) ** 0.5:.4f}")
    print(f"  cosine(A, B) = {s:+.4f}")

print("\n" + "=" * 80)
print("TÓM TẮT")
print("=" * 80)
for i, s in enumerate(scores, 1):
    label = "CAO" if s >= 0.5 else ("TRUNG BÌNH" if s >= 0.2 else "THẤP")
    print(f"  Cặp {i}: {s:+.4f}  ({label})")
print(f"  Trung bình: {sum(scores)/len(scores):+.4f}")
print(f"  Cao nhất  : {max(scores):+.4f} (cặp {scores.index(max(scores))+1})")
print(f"  Thấp nhất : {min(scores):+.4f} (cặp {scores.index(min(scores))+1})")