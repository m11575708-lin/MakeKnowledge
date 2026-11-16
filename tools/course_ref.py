"""course_ref.py — 依第 5–7 週講義公式自行實作的「對照程式」（不是課堂工具）。

為什麼有這支程式：課堂工具（regress.py、logit.py、tree.py…）沒有提供給學生，無法直接拿來對答案。
所以照講義「★例題的完整過程」與附錄逐步表上的公式，用 Python 標準函式庫重寫一份；
先用 `python tools/course_ref.py selftest` 重現講義例題的數字，全部對上後，才拿來對本專案的 Skill。

公式依據（講義頁碼為各週簡報）：
  第 5 週：最小平方、SSE／MAE／RMSE／R²、多元迴歸、時間切分、標準化梯度下降、邏輯迴歸、門檻與成本
  第 6 週：熵、資訊增益、吉尼係數、歐氏距離、以物品為基礎的協同過濾（餘弦、沒評分當 0、取最像的 k 本）
  第 7 週：K 平均（指定起點、跑到沒人換群）、SSE、反向傳播一步（E ＝ ½(ŷ−y)²、δo、δh）

只用 Python 標準函式庫。
"""
import csv
import math
import sys


# ---------------------------------------------------------------- 第 5 週：線性迴歸
def mean(v):
    return sum(v) / len(v)


def ls(x, y):
    """簡單線性迴歸的最小平方解：回傳 (a, b, Sxx, Sxy, Syy)。"""
    mx, my = mean(x), mean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    syy = sum((yi - my) ** 2 for yi in y)
    b = sxy / sxx
    return my - b * mx, b, sxx, sxy, syy


def metrics(y, yhat):
    """SSE、MAE、RMSE、R²（R² 以 y 自己的平均為基準）。"""
    e = [a - b for a, b in zip(y, yhat)]
    sse = sum(v * v for v in e)
    my = mean(y)
    sst = sum((v - my) ** 2 for v in y)
    return {"sse": sse, "mae": mean([abs(v) for v in e]), "rmse": math.sqrt(sse / len(e)),
            "r2": 1 - sse / sst if sst > 0 else float("nan")}


def solve(A, b):
    """高斯消去（部分選主元）解 A x = b。"""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            raise ValueError("矩陣奇異，無法求解")
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]


def multi(X, y):
    """多元迴歸的正規方程 (XᵀX)β = Xᵀy；X 不含截距欄，回傳 [截距, b1, b2, …]。"""
    Z = [[1.0] + list(r) for r in X]
    k = len(Z[0])
    XtX = [[sum(z[i] * z[j] for z in Z) for j in range(k)] for i in range(k)]
    Xty = [sum(z[i] * t for z, t in zip(Z, y)) for i in range(k)]
    return solve(XtX, Xty)


def predict_multi(beta, X):
    return [beta[0] + sum(b * v for b, v in zip(beta[1:], r)) for r in X]


def gd_standardized(x, y, alpha=0.1, steps=50):
    """講義的梯度下降：x 先標準化（母體標準差），MSE 的坡度，起點 a′＝b′＝0。回傳每一步的 (a′, b′)。"""
    mx = mean(x)
    sd = math.sqrt(mean([(v - mx) ** 2 for v in x]))
    z = [(v - mx) / sd for v in x]
    a, b, hist = 0.0, 0.0, []
    for _ in range(steps):
        e = [yi - (a + b * zi) for zi, yi in zip(z, y)]
        da = -2 * sum(e) / len(e)
        db = -2 * sum(ei * zi for ei, zi in zip(e, z)) / len(e)
        a, b = a - alpha * da, b - alpha * db
        hist.append((a, b))
    return hist, mx, sd


# ---------------------------------------------------------------- 第 5 週：邏輯迴歸
def sigmoid(z):
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def logit_mle(X, y, iters=100):
    """最大概似（牛頓法，等同把平均交叉熵降到最低）。X 不含截距欄，回傳 [截距, w1, …]。"""
    Z = [[1.0] + list(r) for r in X]
    k = len(Z[0])
    w = [0.0] * k
    for _ in range(iters):
        p = [sigmoid(sum(a * b for a, b in zip(w, z))) for z in Z]
        g = [sum((pi - yi) * z[j] for pi, yi, z in zip(p, y, Z)) for j in range(k)]
        H = [[sum(pi * (1 - pi) * z[i] * z[j] for pi, z in zip(p, Z)) for j in range(k)] for i in range(k)]
        step = solve(H, g)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-12:
            break
    return w


def logit_gd(x, y, alpha=1.0, steps=200):
    """講義的訓練法（第 5 週 P.39）：x 先標準化（母體標準差），平均交叉熵的坡度，起點 b＝w＝0，走 steps 步。
    回傳 (每一步的 (b′, w′, 交叉熵), 平均, 標準差)。"""
    mx = mean(x)
    sd = math.sqrt(mean([(v - mx) ** 2 for v in x]))
    z = [(v - mx) / sd for v in x]
    b, w, hist = 0.0, 0.0, []
    for _ in range(steps):
        p = [sigmoid(b + w * zi) for zi in z]
        gb = sum(pi - yi for pi, yi in zip(p, y)) / len(y)
        gw = sum((pi - yi) * zi for pi, yi, zi in zip(p, y, z)) / len(y)
        b, w = b - alpha * gb, w - alpha * gw
        p = [sigmoid(b + w * zi) for zi in z]
        ce = -mean([yi * math.log(pi) + (1 - yi) * math.log(1 - pi) for pi, yi in zip(p, y)])
        hist.append((b, w, ce))
    return hist, mx, sd


def confusion(y, p, threshold):
    """門檻：p ≥ threshold 判 1。回傳 TP、FP、FN、TN。"""
    tp = sum(1 for a, q in zip(y, p) if q >= threshold and a == 1)
    fp = sum(1 for a, q in zip(y, p) if q >= threshold and a == 0)
    fn = sum(1 for a, q in zip(y, p) if q < threshold and a == 1)
    tn = sum(1 for a, q in zip(y, p) if q < threshold and a == 0)
    return tp, fp, fn, tn


def cost(y, p, threshold, c_fp_alert, c_fn):
    """講義的成本：警示的每一筆都花 c_fp_alert（含 TP），漏掉的每一筆花 c_fn。"""
    tp, fp, fn, tn = confusion(y, p, threshold)
    return (tp + fp) * c_fp_alert + fn * c_fn


# ---------------------------------------------------------------- 第 6 週：決策樹
def entropy(counts):
    n = sum(counts)
    return -sum(c / n * math.log2(c / n) for c in counts if c)


def gini(counts):
    n = sum(counts)
    return 1 - sum((c / n) ** 2 for c in counts)


def gain(parent, groups, crit=entropy):
    """parent、groups 都是各類別的筆數；回傳「分之前 − 依筆數加權的分之後」。"""
    n = sum(parent)
    return crit(parent) - sum(sum(g) / n * crit(g) for g in groups)


def best_numeric_split(xs, ys, crit=gini):
    """數值欄位：相鄰兩個不同值的中點當候選切點，回傳 (最佳切點, 下降量)。"""
    labels = sorted(set(ys))
    def cnt(sub):
        return [sum(1 for v in sub if v == c) for c in labels]
    vals = sorted(set(xs))
    best = (None, -1.0)
    parent = cnt(ys)
    for lo, hi in zip(vals, vals[1:]):
        t = (lo + hi) / 2
        left = [y for x, y in zip(xs, ys) if x <= t]
        right = [y for x, y in zip(xs, ys) if x > t]
        g = gain(parent, [cnt(left), cnt(right)], crit)
        if g > best[1] + 1e-12:
            best = (t, g)
    return best


# ---------------------------------------------------------------- 第 6 週：距離與協同過濾
def euclid(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def item_cf_predict(ratings, user, k=2, min_rated=2):
    """講義的「以物品為基礎」：餘弦相似度（沒評分當 0，只用評過 ≥ min_rated 本的讀者），
    對沒評過的物品，取該讀者評過、最像的 k 個物品，預測 ＝ Σ相似度×自己的分 ÷ Σ相似度。"""
    items = []
    for r in ratings.values():
        for i in r:
            if i not in items:
                items.append(i)
    active = [u for u in ratings if len(ratings[u]) >= min_rated]
    col = {i: [ratings[u].get(i, 0) for u in active] for i in items}
    norm = {i: math.sqrt(sum(v * v for v in col[i])) for i in items}
    def sim(a, b):
        d = sum(x * y for x, y in zip(col[a], col[b]))
        return d / (norm[a] * norm[b]) if norm[a] and norm[b] else 0.0
    mine = ratings[user]
    out = {}
    for i in items:
        if i in mine:
            continue
        neigh = sorted([j for j in items if j in mine], key=lambda j: (-round(sim(i, j), 9), items.index(j)))[:k]
        den = sum(sim(i, j) for j in neigh)
        out[i] = sum(sim(i, j) * mine[j] for j in neigh) / den if den > 0 else None
    return out


# ---------------------------------------------------------------- 第 7 週：K 平均與反向傳播
def kmeans(points, centers, max_rounds=100):
    """指定起點，跑到沒有人換群；回傳 (中心, 每點所屬群, SSE, 輪數)。"""
    assign = None
    for rnd in range(1, max_rounds + 1):
        new = [min(range(len(centers)), key=lambda c: (euclid(p, centers[c]), c)) for p in points]
        if new == assign:
            break
        assign = new
        centers = [[mean([p[d] for p, a in zip(points, assign) if a == c]) for d in range(len(points[0]))]
                   if any(a == c for a in assign) else centers[c] for c in range(len(centers))]
    sse = sum(euclid(p, centers[a]) ** 2 for p, a in zip(points, assign))
    return centers, assign, sse, rnd


def backprop_step(W, b, v, c, x, y, eta):
    """2–2–1、sigmoid、E ＝ ½(ŷ − y)²；先用舊權重算完全部梯度再一起更新。"""
    h = [sigmoid(sum(wi * xi for wi, xi in zip(W[j], x)) + b[j]) for j in range(len(W))]
    yhat = sigmoid(sum(vj * hj for vj, hj in zip(v, h)) + c)
    E = 0.5 * (yhat - y) ** 2
    do = (yhat - y) * yhat * (1 - yhat)
    dh = [do * v[j] * h[j] * (1 - h[j]) for j in range(len(h))]
    W2 = [[W[j][i] - eta * dh[j] * x[i] for i in range(len(x))] for j in range(len(W))]
    b2 = [b[j] - eta * dh[j] for j in range(len(b))]
    v2 = [v[j] - eta * do * h[j] for j in range(len(v))]
    c2 = c - eta * do
    h2 = [sigmoid(sum(wi * xi for wi, xi in zip(W2[j], x)) + b2[j]) for j in range(len(W2))]
    yhat2 = sigmoid(sum(vj * hj for vj, hj in zip(v2, h2)) + c2)
    return {"h": h, "yhat": yhat, "E": E, "do": do, "dh": dh, "W": W2, "b": b2, "v": v2, "c": c2,
            "yhat_after": yhat2, "E_after": 0.5 * (yhat2 - y) ** 2}


# ---------------------------------------------------------------- 第 7 週：感知器、階層式分群（講義例題資料是圖片，未能用例題驗證）
def perceptron(Z, y, eta=0.1, max_epochs=200, w=None, b=0.0):
    """講義的感知器：分數 w·x ＋ b ＞ 0 判 1；判錯才改 w ← w ＋ η(y − ŷ)x、b ← b ＋ η(y − ŷ)。
    依給定順序逐筆學，整輪沒有錯就停。回傳 (w, b, 輪數, 每輪錯幾筆)。"""
    w = list(w) if w else [0.0] * len(Z[0])
    errs = []
    for ep in range(1, max_epochs + 1):
        m = 0
        for z, t in zip(Z, y):
            pred = 1 if sum(a * c for a, c in zip(w, z)) + b > 0 else 0
            if pred != t:
                w = [a + eta * (t - pred) * c for a, c in zip(w, z)]
                b += eta * (t - pred)
                m += 1
        errs.append(m)
        if m == 0:
            break
    return w, b, ep, errs


def hier(X, link="average"):
    """凝聚式階層分群：一開始每筆自成一群，每次合併距離最近的兩群。
    single＝兩群最近兩點、complete＝最遠兩點、average＝所有配對平均。回傳每步 (群 A, 群 B, 高度)。"""
    groups = [[i] for i in range(len(X))]
    D = {(i, j): euclid(X[i], X[j]) for i in range(len(X)) for j in range(i + 1, len(X))}
    def gd(a, b):
        ds = [D[(min(i, j), max(i, j))] for i in a for j in b]
        return min(ds) if link == "single" else max(ds) if link == "complete" else sum(ds) / len(ds)
    merges = []
    while len(groups) > 1:
        best = min(((gd(groups[i], groups[j]), i, j) for i in range(len(groups)) for j in range(i + 1, len(groups))))
        h, i, j = best
        merges.append((sorted(groups[i]), sorted(groups[j]), h))
        groups[i] = groups[i] + groups[j]
        del groups[j]
    return merges


def cut(merges, n, threshold):
    """在高度 threshold 切開：高度 ≤ threshold 的合併才做。回傳群的清單。"""
    parent = list(range(n))
    def find(a):
        while parent[a] != a:
            a = parent[a]
        return a
    for a, b, h in merges:
        if h <= threshold:
            parent[find(b[0])] = find(a[0])
    out = {}
    for i in range(n):
        out.setdefault(find(i), []).append(i)
    return sorted(out.values())


# ---------------------------------------------------------------- 講義例題自我檢查
def _num(s):
    return float(str(s).replace(",", ""))


def selftest(course_dir):
    """course_dir：三週學生參考資料 zip 解壓縮後的根目錄（內含 第 5、6 週的範例 CSV）。"""
    import glob
    import os
    rows, ok = [], True

    def check(name, got, want, tol):
        nonlocal ok
        good = abs(got - want) <= tol
        ok &= good
        rows.append((name, round(got, 6), want, "OK" if good else "XX"))

    # 第 5 週：鮮果日和 2025 年 12 個月（P.71）
    f = glob.glob(os.path.join(course_dir, "**/ad-revenue-forecast/v2/examples/xianguo_2025_monthly.csv"), recursive=True)[0]
    data = [r for r in csv.DictReader(open(f, encoding="utf-8-sig")) if r["month"].startswith("2025")]
    data.sort(key=lambda r: r["month"])
    x = [_num(r["ad_budget"]) for r in data]
    y = [_num(r["revenue"]) for r in data]
    a, b, sxx, sxy, syy = ls(x, y)
    check("迴歸 Sxx", sxx, 1556, 0.5); check("迴歸 Sxy", sxy, 17116, 0.5); check("迴歸 Syy", syy, 206220, 0.5)
    check("迴歸 b", b, 11, 0.005); check("迴歸 a", a, 250, 0.05)
    m = metrics(y, [a + b * v for v in x])
    check("SSE", m["sse"], 17944, 0.5); check("MAE", m["mae"], 34.17, 0.005)
    check("RMSE", m["rmse"], 38.67, 0.005); check("R²", m["r2"], 0.913, 0.0005)
    hist, mx, sd = gd_standardized(x, y)
    check("標準差", sd, 11.387, 0.0005)
    check("GD 第 1 步 a′", hist[0][0], 160, 0.005); check("GD 第 1 步 b′", hist[0][1], 25.05, 0.005)
    check("GD 第 2 步 a′", hist[1][0], 288, 0.005); check("GD 第 2 步 b′", hist[1][1], 45.09, 0.005)
    check("GD 第 50 步 a′", hist[49][0], 799.99, 0.005); check("GD 第 50 步 b′", hist[49][1], 125.26, 0.005)
    peak = [1.0 if r["month"] in ("2025-01", "2025-11") else 0.0 for r in data]
    beta = multi([[xi, pk] for xi, pk in zip(x, peak)], y)
    check("多元 截距", beta[0], 333.2, 0.05); check("多元 廣告", beta[1], 9.03, 0.005); check("多元 旺季", beta[2], 93.09, 0.005)
    check("多元 R²", metrics(y, predict_multi(beta, [[xi, pk] for xi, pk in zip(x, peak)]))["r2"], 0.954, 0.0005)
    a9, b9, *_ = ls(x[:9], y[:9])
    check("切分 1–9 月 a", a9, 243.55, 0.005); check("切分 1–9 月 b", b9, 11.227, 0.0005)
    check("切分 測試 RMSE", metrics(y[9:], [a9 + b9 * v for v in x[9:]])["rmse"], 49.69, 0.005)

    # 第 5 週：會員流失（P.39、P.72 附錄逐步表）
    f = glob.glob(os.path.join(course_dir, "**/member-churn-alert/v2/examples/members.csv"), recursive=True)[0]
    def clean(r):   # 範例檔刻意放了空白、非數字、負數、答案不是 0／1 的列，講義清理後各 20 位
        try:
            return (r.get("dataset") in ("train", "test") and float(r["recency_days"]) >= 0
                    and float(r["complaints_90d"]) >= 0 and r["churned"] in ("0", "1"))
        except (ValueError, TypeError):
            return False
    mem, seen = [], set()
    for r in csv.DictReader(open(f, encoding="utf-8-sig")):
        if r.get("customer_id") in seen:      # 會員編號重複只留第一筆
            continue
        seen.add(r.get("customer_id"))
        if clean(r):
            mem.append(r)
    tr = [r for r in mem if r["dataset"] == "train"]
    te = [r for r in mem if r["dataset"] == "test"]
    xd, yd = [_num(r["recency_days"]) for r in tr], [int(r["churned"]) for r in tr]
    hist, mx, sd = logit_gd(xd, yd)
    check("邏輯 天數標準差", sd, 22.95, 0.005)
    check("邏輯 第 1 步 w′", hist[0][1], 0.355, 0.0005); check("邏輯 第 1 步交叉熵", hist[0][2], 0.5826, 0.00005)
    check("邏輯 第 200 步 w′", hist[199][1], 2.713, 0.0015); check("邏輯 第 200 步 b′", hist[199][0], 0.249, 0.0005)
    check("邏輯 第 200 步交叉熵", hist[199][2], 0.3605, 0.00005)
    # 講義公布的係數 −3.996、0.1183 是收斂後的值（約第 250 步起不再變，等於最大概似解）；
    # 同頁寫「第 200 步」，第 200 步換回原單位是 −3.995、0.11822，差在第 4 位，判讀不受影響。
    w = logit_mle([[v] for v in xd], yd)
    check("邏輯 截距（收斂後）", w[0], -3.996, 0.0005); check("邏輯 天數係數（收斂後）", w[1], 0.1183, 0.00005)
    yt = [int(r["churned"]) for r in te]
    pt = [sigmoid(w[0] + w[1] * _num(r["recency_days"])) for r in te]
    want = {0.1: (8, 7, 0, 5, 1500), 0.3: (7, 5, 1, 7, 3200), 0.5: (6, 3, 2, 9, 4900), 0.9: (3, 1, 5, 11, 10400)}
    for t, (tp, fp, fn, tn, cst) in want.items():
        got = confusion(yt, pt, t)
        check(f"門檻 {t} TP/FP/FN/TN 全對", float(got == (tp, fp, fn, tn)), 1.0, 0)
        check(f"門檻 {t} 總成本", cost(yt, pt, t, 100, 2000), cst, 0)

    # 第 6 週：打球 14 天（P.5，用各群的去／不去天數）
    check("熵 根節點", entropy([9, 5]), 0.94, 0.0005)
    check("增益 天氣", gain([9, 5], [[4, 1], [4, 0], [1, 4]]), 0.425, 0.0005)
    check("增益 有空", gain([9, 5], [[8, 2], [1, 3]]), 0.193, 0.0005)
    check("增益 風", gain([9, 5], [[6, 2], [3, 3]]), 0.048, 0.0005)
    check("吉尼 西瓜根節點（6 甜 6 不甜）", gini([6, 6]), 0.5, 0)

    # 第 6 週：圖書館協同過濾（學生參考資料 README：cf.py itempredict R1 --k 2）
    f = glob.glob(os.path.join(course_dir, "**/library-also-liked/v1/examples/ratings.csv"), recursive=True)[0]
    rat = {}
    for r in csv.DictReader(open(f, encoding="utf-8-sig")):
        if r.get("reader") and r.get("book") and r.get("rating", "").strip().isdecimal() and 1 <= int(r["rating"]) <= 5:
            rat.setdefault(r["reader"], {})[r["book"]] = int(r["rating"])
    pr = item_cf_predict(rat, "R1", k=2)
    check("協同過濾 R1 奇幻小說", pr["奇幻小說"], 4.48, 0.005)
    check("協同過濾 R1 漫畫", pr["漫畫"], 2.61, 0.005)
    check("協同過濾 R1 旅遊書", pr["旅遊書"], 2.65, 0.005)

    # 第 7 週：班遊上車點（P.72–73）
    pts = {"01": (2, 11), "02": (4, 13), "03": (1, 9), "04": (5, 10), "05": (10, 3), "06": (13, 5),
           "07": (11, 1), "08": (14, 3), "09": (9, 9), "10": (12, 11), "11": (10, 13), "12": (14, 9)}
    check("距離 01→07", euclid(pts["01"], pts["07"]), 13.45, 0.005)
    check("距離 09→11", euclid(pts["09"], pts["11"]), 4.12, 0.005)
    cen, asg, sse, rnd = kmeans(list(pts.values()), [pts["03"], pts["07"], pts["11"]])
    check("K 平均 中心 1 x", cen[0][0], 3, 0.005); check("K 平均 中心 1 y", cen[0][1], 10.75, 0.005)
    check("K 平均 中心 3 x", cen[2][0], 11.25, 0.005); check("K 平均 SSE", sse, 62.5, 0.005)

    # 第 7 週：盆栽網路反向傳播一步（P.32、P.74；c 由 ŷ＝0.5587 反推為 −0.1）
    r = backprop_step([[0.6, -0.4], [-0.5, 0.3]], [0.2, 0.4], [0.9, -0.6], -0.1, [1, 0], 1, 1.0)
    check("反傳 ŷ", r["yhat"], 0.5587, 0.00005); check("反傳 E", r["E"], 0.0974, 0.00005)
    check("反傳 δo", r["do"], -0.1088, 0.00005)
    check("反傳 δh1", r["dh"][0], -0.0209, 0.00005); check("反傳 δh2", r["dh"][1], 0.0163, 0.00005)
    check("反傳 新 w11", r["W"][0][0], 0.6209, 0.00005); check("反傳 新 b2", r["b"][1], 0.3837, 0.00005)
    check("反傳 新 v1", r["v"][0], 0.9751, 0.00005)
    check("反傳 更新後 ŷ", r["yhat_after"], 0.6069, 0.00005); check("反傳 更新後 E", r["E_after"], 0.0773, 0.00005)
    return ok, rows


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "selftest":
        ok, rows = selftest(sys.argv[2])
        for name, got, want, flag in rows:
            print(f"{flag}  {name:28s} 對照程式 {got:<14} 講義 {want}")
        print(f"\n{'全部' if ok else '並非全部'}對上講義（共 {len(rows)} 項）")
        sys.exit(0 if ok else 1)
    print("用法：python tools/course_ref.py selftest <學生參考資料解壓縮的資料夾>")
