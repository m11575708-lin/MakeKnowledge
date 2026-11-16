"""把全國法規資料庫下載的法規 PDF 拆成「一條一個 .md」，放進 docs/ 給 skill_01 檢索，並產生 data/catalog_manifest.json。

為什麼一條一個檔：skill_01 以「一個檔案＝一份文件」計算相似度，整部法規放一個檔只能查到「整部法規」，
無法回答「依第幾條」。

用法（需先安裝 poppler 的 pdftotext）：
    pdftotext -layout 職業安全衛生法.pdf            <txt 資料夾>/osh_act.txt
    pdftotext -layout 危險性機械及設備安全檢查規則.pdf <txt 資料夾>/dme_rules.txt
    python tools/split_laws.py <txt 資料夾> docs data/catalog_manifest.json

法規修正時：從全國法規資料庫重新下載 PDF，更新下方 LAWS 的修正日期，再執行一次。
只用 Python 標準函式庫。
"""
import json, re, sys, os

LAWS = [
    {"txt": "osh_act.txt", "key": "osh_act", "name": "職業安全衛生法", "pcode": "N0060001",
     "amended": "民國 114 年 12 月 19 日", "updated_at": "2025-12-19", "pending": {}},
    {"txt": "dme_rules.txt", "key": "dme_rules", "name": "危險性機械及設備安全檢查規則", "pcode": "N0060039",
     "amended": "民國 114 年 12 月 23 日", "updated_at": "2025-12-23",
     "pending": {"3": "依第 168 條規定，本條 114 年 12 月 23 日修正條文自發布後一年施行（民國 115 年 12 月 23 日）；施行前仍適用修正前條文。",
                 "19": "同上，自民國 115 年 12 月 23 日施行。", "29": "同上，自民國 115 年 12 月 23 日施行。"}},
]
LICENSE = "依著作權法第 9 條，法律及命令不得為著作權之標的（來源：全國法規資料庫）"
ART_RE = re.compile(r"^\s*第\s*([0-9]+(?:-[0-9]+)?)\s*條\s*$")
CH_RE = re.compile(r"^\s*第\s*([一二三四五六七八九十百]+)\s*章\s*(.+?)\s*$")
SEC_RE = re.compile(r"^\s*第\s*([一二三四五六七八九十百]+)\s*節\s*(.+?)\s*$")
PARA_RE = re.compile(r"^(\d+)\s{2,}(.*)$")          # 項次（行首數字）
ITEM_RE = re.compile(r"^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\d+\.)")

def norm_lines(raw):
    out = []
    for line in raw:
        line = line.replace("\f", "").rstrip()
        s = line.strip()
        if not s:
            continue
        m = PARA_RE.match(s)
        if m:                                   # 新的一項
            out.append({"para": m.group(1), "text": m.group(2).strip()})
        elif ITEM_RE.match(s) or not out:       # 款、目另起一行
            out.append({"para": None, "text": s})
        else:                                   # 版面換行 → 接回上一行
            out[-1]["text"] += s
    return out

def parse(law, txt_dir):
    lines = open(os.path.join(txt_dir, law["txt"]), encoding="utf-8").read().split("\n")
    arts, chapter, section, cur, body = [], "", "", None, []
    cur_where = ("", "")
    for line in lines:
        s = line.replace("\f", "").strip()
        if ART_RE.match(s):
            if cur: arts.append((cur, cur_where[0], cur_where[1], body))
            cur, body = ART_RE.match(s).group(1), []
            cur_where = (chapter, section)          # 章節取「條號出現當下」的值
            continue
        if CH_RE.match(s) and not s.endswith("條"):
            chapter, section = re.sub(r"章 之([一二三四五六七八九十]+) ", r"章之\1 ", f"第{CH_RE.match(s).group(1)}章 {CH_RE.match(s).group(2)}"), ""
            continue
        if SEC_RE.match(s):
            section = f"第{SEC_RE.match(s).group(1)}節 {SEC_RE.match(s).group(2)}"
            continue
        if cur: body.append(line)
    if cur: arts.append((cur, cur_where[0], cur_where[1], body))
    return arts

def main(txt_dir, outdir):
    os.makedirs(outdir, exist_ok=True)
    manifest, summary = [], []
    for law in LAWS:
        arts = parse(law, txt_dir)
        nums = [a[0] for a in arts]
        assert len(nums) == len(set(nums)), "條號重複"
        for num, chapter, section, body in arts:
            paras = norm_lines(body)
            text_lines = []
            for p in paras:
                text_lines.append(f"{p['para']}. {p['text']}" if p["para"] else p["text"])
            content = "\n".join(text_lines).strip() or "（刪除）"
            fn = f"law_{law['key']}_art{num.split('-')[0].zfill(3)}{('-' + num.split('-')[1]) if '-' in num else ''}.md"
            url = f"https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode={law['pcode']}&flno={num}"
            where = "、".join(x for x in (chapter, section) if x)
            # 條文檔只放「標題（含章節）＋條文」；修正日期、來源網址、授權記在 catalog_manifest.json，
            # 避免被 skill_01 當成答案內容，也避免每份文件都帶同樣的網址字詞干擾相似度。
            md = [f"# {law['name']} 第 {num} 條" + (f"（{where}）" if where else ""), "", content]
            if num in law["pending"]:
                md += ["", f"（施行狀態：{law['pending'][num]}）"]
            md.append("")
            open(os.path.join(outdir, fn), "w", encoding="utf-8").write("\n".join(md))
            manifest.append({"file": fn, "source_name": f"{law['name']} 第 {num} 條", "category": "職安法規",
                             "updated_at": law["updated_at"], "license_type": LICENSE, "source_url": url, "is_public": True})
        summary.append((law["name"], len(arts), nums[0], nums[-1]))
    return manifest, summary

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("用法：python tools/split_laws.py <txt 資料夾> <輸出 docs 資料夾> <manifest 輸出路徑>")
    manifest, summary = main(sys.argv[1], sys.argv[2])
    with open(sys.argv[3], "w", encoding="utf-8") as f:
        json.dump({"documents": manifest}, f, ensure_ascii=False, indent=1)
    for s in summary: print(s)
    print("files:", len(manifest))
