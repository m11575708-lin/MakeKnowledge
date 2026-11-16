"""
_cart.py - 純標準庫的多類別 CART 決策樹、代價複雜度剪枝與規則導出（page11 使用）

節點以 dict 表示，方便深拷貝與轉 JSON：
  {"counts": [各類別樣本數], "n": 樣本數, "impurity": Gini, "feature": 索引或 None,
   "threshold": 切分值, "left": 節點, "right": 節點}      （feature 為 None 即葉節點）
切分規則：x[feature] <= threshold 走左邊，否則走右邊。

剪枝：最弱連結 (weakest link) 代價複雜度剪枝。
  R(t)   = 節點 t 當葉節點時的誤分類比例（誤分類數 / 訓練總樣本數 N）
  R(T_t) = 以 t 為根的子樹中，所有葉節點 R 的總和；|T_t| = 該子樹葉節點數
  g(t)   = (R(t) - R(T_t)) / (|T_t| - 1)    ← 每多一個葉節點能換到多少誤差下降
  每次剪掉 g 最小的內部節點，α 序列非遞減；給定 α，最佳子樹是序列中「α_k ≤ α」的最後一棵，
  等價於最小化 R_α(T) = R(T) + α|T|。
"""

import copy

try:
    from ._forest import gini
except ImportError:
    from _forest import gini


def _make_node(y, idx, n_classes):
    counts = [0] * n_classes
    for i in idx:
        counts[y[i]] += 1
    n = len(idx)
    return {"counts": counts, "n": n, "impurity": gini(counts, n), "feature": None, "threshold": None,
            "left": None, "right": None}


def is_leaf(node) -> bool:
    return node["feature"] is None


def fit_cart(X, y, n_classes, max_depth=10, min_leaf=2, min_split=4):
    """遞迴切分：每個節點掃描所有特徵與所有相鄰值的中點，選吉尼不純度下降最大者。"""
    n_features = len(X[0])

    def grow(idx, depth):
        node = _make_node(y, idx, n_classes)
        n = node["n"]
        if depth >= max_depth or n < min_split or node["impurity"] == 0.0:
            return node
        best = None   # (gain, feature, threshold)
        for f in range(n_features):
            order = sorted(idx, key=lambda i: X[i][f])
            left = [0] * n_classes
            right = node["counts"][:]
            for pos in range(n - 1):
                c = y[order[pos]]
                left[c] += 1
                right[c] -= 1
                if X[order[pos]][f] == X[order[pos + 1]][f]:
                    continue
                nl, nr = pos + 1, n - pos - 1
                if nl < min_leaf or nr < min_leaf:
                    continue
                gain = node["impurity"] - (nl * gini(left, nl) + nr * gini(right, nr)) / n
                if best is None or gain > best[0] + 1e-12:
                    best = (gain, f, (X[order[pos]][f] + X[order[pos + 1]][f]) / 2.0)
        if best is None or best[0] <= 1e-12:
            return node
        gain, f, thr = best
        node["feature"], node["threshold"], node["gain"] = f, thr, gain
        node["left"] = grow([i for i in idx if X[i][f] <= thr], depth + 1)
        node["right"] = grow([i for i in idx if X[i][f] > thr], depth + 1)
        return node

    return grow(list(range(len(X))), 0)


def majority(node) -> int:
    return max(range(len(node["counts"])), key=lambda c: (node["counts"][c], -c))


def find_leaf(node, x):
    while not is_leaf(node):
        node = node["left"] if x[node["feature"]] <= node["threshold"] else node["right"]
    return node


def predict(node, x) -> int:
    return majority(find_leaf(node, x))


def decision_path(node, x, feature_names):
    """回傳走過的條件清單 [{feature, label?, op, threshold, value}]。"""
    out = []
    while not is_leaf(node):
        go_left = x[node["feature"]] <= node["threshold"]
        out.append({"feature": feature_names[node["feature"]], "op": "<=" if go_left else ">",
                    "threshold": node["threshold"], "value": x[node["feature"]]})
        node = node["left"] if go_left else node["right"]
    return out


def n_leaves(node) -> int:
    return 1 if is_leaf(node) else n_leaves(node["left"]) + n_leaves(node["right"])


def depth(node) -> int:
    return 0 if is_leaf(node) else 1 + max(depth(node["left"]), depth(node["right"]))


def n_splits(node) -> int:
    return 0 if is_leaf(node) else 1 + n_splits(node["left"]) + n_splits(node["right"])


def accuracy(node, X, y) -> float:
    return sum(1 for xi, yi in zip(X, y) if predict(node, xi) == yi) / len(X)


def confusion_matrix(node, X, y, n_classes):
    """列＝真實類別、欄＝預測類別。"""
    m = [[0] * n_classes for _ in range(n_classes)]
    for xi, yi in zip(X, y):
        m[yi][predict(node, xi)] += 1
    return m


def gini_importance(node, n_features, total_n=None):
    """各特徵的 Gini 下降量加總：Σ (n_t/N)·[I(t) - n_l/n_t·I(l) - n_r/n_t·I(r)]，回傳未歸一化列表。"""
    total_n = total_n or node["n"]
    raw = [0.0] * n_features

    def walk(nd):
        if is_leaf(nd):
            return
        l, r = nd["left"], nd["right"]
        dec = nd["n"] * nd["impurity"] - l["n"] * l["impurity"] - r["n"] * r["impurity"]
        raw[nd["feature"]] += dec / total_n
        walk(l)
        walk(r)

    walk(node)
    return raw


def prune_sequence(root, total_n):
    """最弱連結剪枝；回傳 [{"alpha", "tree", "leaves"}]，第 0 筆為完整樹 (alpha=0)。"""
    cur = copy.deepcopy(root)
    seq = [{"alpha": 0.0, "tree": copy.deepcopy(cur), "leaves": n_leaves(cur)}]
    alpha_prev = 0.0
    while not is_leaf(cur):
        best = [None]   # (g, leaves, node)

        def walk(nd):
            if is_leaf(nd):
                return (nd["n"] - max(nd["counts"])) / total_n, 1
            rl, ll = walk(nd["left"])
            rr, lr = walk(nd["right"])
            r_sub, leaves = rl + rr, ll + lr
            r_t = (nd["n"] - max(nd["counts"])) / total_n
            g = (r_t - r_sub) / (leaves - 1)
            if best[0] is None or g < best[0][0] - 1e-15 or (abs(g - best[0][0]) <= 1e-15 and leaves < best[0][1]):
                best[0] = (g, leaves, nd)
            return r_sub, leaves

        walk(cur)
        g, _, node = best[0]
        node["feature"] = node["threshold"] = node["left"] = node["right"] = None
        alpha_prev = max(alpha_prev, g)
        seq.append({"alpha": alpha_prev, "tree": copy.deepcopy(cur), "leaves": n_leaves(cur)})
    return seq


def pick_by_alpha(seq, alpha):
    """最小代價複雜度子樹：α_k ≤ α 的最後一棵。"""
    chosen = seq[0]
    for item in seq:
        if item["alpha"] <= alpha + 1e-12:
            chosen = item
    return chosen


def extract_rules(root, feature_names, class_names, digits=2):
    """每條根到葉的路徑轉成一條 IF-THEN 規則；同一特徵的多個條件合併為最緊的上下界。"""
    rules = []

    def walk(nd, lo, hi):
        if is_leaf(nd):
            conds = []
            for f, name in enumerate(feature_names):
                if f in lo:
                    conds.append({"feature": name, "op": ">", "value": round(lo[f], digits)})
                if f in hi:
                    conds.append({"feature": name, "op": "<=", "value": round(hi[f], digits)})
            m = majority(nd)
            rules.append({"conditions": conds, "class_index": m, "class": class_names[m], "n": nd["n"],
                          "purity": nd["counts"][m] / nd["n"] if nd["n"] else 0.0, "counts": nd["counts"][:], "_leaf": nd})
            return
        f, t = nd["feature"], nd["threshold"]
        walk(nd["left"], lo, {**hi, f: min(hi.get(f, t), t)})
        walk(nd["right"], {**lo, f: max(lo.get(f, t), t)}, hi)

    walk(root, {}, {})
    for r in rules:
        r["text"] = "IF " + " AND ".join(f"{c['feature']} {c['op'].replace('<=', '≤')} {c['value']:g}" for c in r["conditions"]) \
                    + f" THEN {r['class']}"
    return rules


def to_json_tree(node, feature_names, class_names, x=None):
    """轉成前端繪圖用的巢狀 dict；若給 x，會標記走過的節點 on_path。"""
    counter = [0]

    def conv(nd, on_path):
        nid = counter[0]
        counter[0] += 1
        m = majority(nd)
        out = {"id": nid, "leaf": is_leaf(nd), "n": nd["n"], "counts": dict(zip(class_names, nd["counts"])),
               "majority": class_names[m], "purity": round(nd["counts"][m] / nd["n"], 4) if nd["n"] else 0.0,
               "on_path": on_path}
        if not is_leaf(nd):
            go_left = x is not None and x[nd["feature"]] <= nd["threshold"]
            out.update({"feature": feature_names[nd["feature"]], "threshold": round(nd["threshold"], 3),
                        "left": conv(nd["left"], on_path and x is not None and go_left),
                        "right": conv(nd["right"], on_path and x is not None and not go_left)})
        return out

    return conv(node, x is not None)
