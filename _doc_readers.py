"""
_doc_readers.py - 匯入用的檔案讀取器（只用標準庫）：文字解碼、CSV、Markdown、PDF 抽字

安全限制（防止惡意或過大的檔案）：
  * 單檔上限 MAX_BYTES、CSV 最多 MAX_ROWS 列 / MAX_COLS 欄、PDF 解壓後最多 MAX_INFLATE 位元組（防 zip bomb）
  * 不執行任何檔案內容，不用 eval / pickle

PDF 抽字是「基本版」：
  * 用 zlib 解開 FlateDecode 串流，抓 BT…ET 文字區塊裡的 Tj / TJ 文字運算子。
  * 只能處理文字型 PDF 且字型為簡單編碼或 UTF-16 十六進位字串者；
    掃描檔（只有圖片）、使用嵌入式子集字型但沒有直接 Unicode 的中文 PDF 通常抽不到可讀文字，
    此時會回報失敗（不寫入亂碼），請改以文字檔或 Markdown 匯入。
"""

import csv
import io
import re
import zlib

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50000
MAX_COLS = 100
MAX_INFLATE = 20 * 1024 * 1024
MAX_STREAMS = 3000
ALLOWED_EXT = (".pdf", ".csv", ".md")


class ReadError(Exception):
    """可預期的讀取失敗（格式錯誤等），訊息會寫入匯入紀錄。"""


def decode_text(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise ReadError("檔案含有二進位內容（NUL 字元），不是文字檔")
    for enc in ("utf-8-sig", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ReadError("無法解碼：不是 UTF-8 或 Big5 編碼的文字檔")


def read_csv(data: bytes):
    """回傳 (headers, rows)；rows 是 list[list[str]]，已去掉標頭列。欄數不一致的列照原樣回傳，由清洗階段判斷。"""
    text = decode_text(data)
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        raise ReadError("CSV 是空的或第一列不是標頭")
    head = lines[0]
    delim = max((",", ";", "\t"), key=lambda d: head.count(d))
    if head.count(delim) == 0:
        raise ReadError("CSV 標頭只有一欄，無法判斷分隔符號（支援逗號、分號、Tab）")
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delim, strict=False)
        headers = [h.strip() for h in next(reader)]
        if len(headers) > MAX_COLS:
            raise ReadError(f"欄位數 {len(headers)} 超過上限 {MAX_COLS}")
        if len(set(headers)) != len(headers) or any(not h for h in headers):
            raise ReadError("CSV 標頭有空白或重複的欄位名稱")
        rows = []
        for r in reader:
            rows.append(r)
            if len(rows) > MAX_ROWS:
                raise ReadError(f"CSV 超過 {MAX_ROWS} 列上限")
    except csv.Error as e:
        raise ReadError(f"CSV 解析失敗：{e}")
    return headers, rows


def read_markdown(data: bytes):
    """回傳段落清單（以空白行分段）。"""
    text = decode_text(data).replace("\r\n", "\n").replace("\r", "\n")
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


# ---------------- PDF ----------------
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_STR_RE = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>", re.S)
_BT_RE = re.compile(rb"BT(.*?)ET", re.S)
_OP_RE = re.compile(rb"(\[(?:\\.|[^\]\\])*\]|\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>)\s*(TJ|Tj)", re.S)


def _unescape(lit: bytes) -> bytes:
    out, i = bytearray(), 0
    m = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12, ord("("): 40, ord(")"): 41, ord("\\"): 92}
    while i < len(lit):
        c = lit[i]
        if c == 92 and i + 1 < len(lit):
            n = lit[i + 1]
            if 48 <= n <= 55:
                j = i + 1
                while j < len(lit) and j < i + 4 and 48 <= lit[j] <= 55:
                    j += 1
                out.append(int(lit[i + 1:j], 8) & 0xFF)
                i = j
                continue
            out.append(m.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return bytes(out)


def _decode_pdf_string(tok: bytes) -> str:
    if tok.startswith(b"("):
        raw = _unescape(tok[1:-1])
    else:
        hx = re.sub(rb"\s+", b"", tok[1:-1])
        if len(hx) % 2:
            hx += b"0"
        raw = bytes.fromhex(hx.decode("ascii"))
    if raw[:2] == b"\xfe\xff":
        return raw[2:].decode("utf-16-be", errors="ignore")
    if len(raw) >= 4 and len(raw) % 2 == 0 and raw[0::2].count(0) >= len(raw) // 2 * 0.6:
        return raw.decode("utf-16-be", errors="ignore")
    return raw.decode("latin-1")


def pdf_paragraphs(data: bytes):
    """回傳 (段落清單, 說明)。每個 BT…ET 區塊視為一個段落。"""
    if not data.startswith(b"%PDF-"):
        raise ReadError("不是有效的 PDF（缺少 %PDF- 檔頭）")
    paras = []
    streams = _STREAM_RE.findall(data)
    if len(streams) > MAX_STREAMS:
        raise ReadError(f"PDF 內含 {len(streams)} 個串流，超過上限 {MAX_STREAMS}")
    budget = MAX_INFLATE
    for raw in streams:
        content = raw
        if raw[:1] in (b"x", b"H"):                      # zlib 標頭常見為 0x78
            try:
                d = zlib.decompressobj()
                content = d.decompress(raw, min(budget, MAX_INFLATE))
                budget -= len(content)
                if d.unconsumed_tail and budget <= 0:
                    raise ReadError("PDF 解壓後內容過大（超過 20MB），已拒絕")
            except zlib.error:
                continue
        if b"BT" not in content:
            continue
        for blk in _BT_RE.findall(content):
            parts = []
            for tok, op in _OP_RE.findall(blk):
                if op == b"Tj":
                    parts.append(_decode_pdf_string(tok))
                else:
                    for piece in re.finditer(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|-?\d+\.?\d*", tok):
                        s = piece.group(0)
                        if s[:1] in (b"(", b"<"):
                            parts.append(_decode_pdf_string(s))
                        elif float(s) < -200:            # 大的負 kerning ≈ 空白
                            parts.append(" ")
            text = "".join(parts).strip()
            if text:
                paras.append(text)
    total = "".join(paras)
    if len(total) < 20:
        raise ReadError("無法從這份 PDF 抽取文字（可能是掃描檔或使用嵌入式字型），請改以文字檔或 Markdown 匯入")
    printable = sum(1 for ch in total if ch.isprintable() or ch.isspace()) / len(total)
    if printable < 0.9:
        raise ReadError(f"PDF 抽出的內容 {100 - printable * 100:.0f}% 是不可顯示字元（字型編碼無法解讀），已拒絕寫入亂碼")
    return paras
