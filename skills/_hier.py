"""
_hier.py - 純標準庫的凝聚階層式分群（page13 的 skill_24 / skill_25 共用）

凝聚法：一開始每台設備自成一群 → 每次合併「距離最近的兩群」→ 直到只剩一群。
距離矩陣用歐氏距離；群間距離用 Lance–Williams 遞推式更新（不必每次回頭算全部點對）：
  single   d(k, i∪j) = min(d(k,i), d(k,j))
  complete d(k, i∪j) = max(d(k,i), d(k,j))
  average  d(k, i∪j) = (n_i·d(k,i) + n_j·d(k,j)) / (n_i + n_j)      （UPGMA）
merge_history 與 scipy 慣例相同：第 s 次合併產生新節點 id = n + s，每筆 [左節點, 右節點, 距離, 新群大小]。
樹的高度（合併距離）在 single / complete / average 下不會倒退（單調）。
共生距離（cophenetic distance）：兩個點在樹上「首次被併入同一群」時的合併距離；
共生相關係數 = corr(原始距離, 共生距離)，越接近 1 代表樹越忠實地保留原始距離結構。
"""

import math

MAX_ITEMS = 150
LINKAGES = ("single", "complete", "average")


def euclid(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def distance_matrix(X):
    n = len(X)
    D = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            D[i][j] = D[j][i] = euclid(X[i], X[j])
    return D


def agglomerate(X, linkage="average"):
    """回傳 {merge_history, leaf_order, cophenetic, dist_matrix}。"""
    n = len(X)
    D0 = distance_matrix(X)
    D = {}                                   # (a, b) a<b → 群間距離，key 用節點 id
    for i in range(n):
        for j in range(i + 1, n):
            D[(i, j)] = D0[i][j]
    size = {i: 1 for i in range(n)}
    children = {}
    active = set(range(n))
    merges = []

    def key(a, b):
        return (a, b) if a < b else (b, a)

    for s in range(n - 1):
        # 找最近的一對（同距離時取 id 小者，結果可重現）
        best, bd = None, float("inf")
        for a in sorted(active):
            for b in sorted(active):
                if b <= a:
                    continue
                d = D[(a, b)]
                if d < bd - 1e-15:
                    best, bd = (a, b), d
        a, b = best
        new = n + s
        merges.append([a, b, bd, size[a] + size[b]])
        children[new] = (a, b)
        size[new] = size[a] + size[b]
        for k in active:
            if k in (a, b):
                continue
            dka, dkb = D[key(k, a)], D[key(k, b)]
            if linkage == "single":
                d = min(dka, dkb)
            elif linkage == "complete":
                d = max(dka, dkb)
            else:
                d = (size[a] * dka + size[b] * dkb) / (size[a] + size[b])
            D[key(k, new)] = d
        active.discard(a)
        active.discard(b)
        active.add(new)

    def leaves(node):
        if node < n:
            return [node]
        l, r = children[node]
        return leaves(l) + leaves(r)

    root = n + n - 2 if n > 1 else 0
    order = leaves(root)
    # 共生距離
    coph = [[0.0] * n for _ in range(n)]
    members = {i: [i] for i in range(n)}
    for s, (a, b, d, _) in enumerate(merges):
        for i in members[a]:
            for j in members[b]:
                coph[i][j] = coph[j][i] = d
        members[n + s] = members[a] + members[b]
    return {"merge_history": merges, "leaf_order": order, "cophenetic": coph, "dist_matrix": D0, "n": n}


def cophenetic_correlation(D0, coph):
    n = len(D0)
    xs, ys = [], []
    for i in range(n):
        for j in range(i + 1, n):
            xs.append(D0[i][j])
            ys.append(coph[i][j])
    if len(xs) < 2:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def cut_tree(merges, n, threshold):
    """距離 ≤ threshold 的合併全部採用，其餘不合併。回傳 labels（依最小成員索引編號 0..k-1）。"""
    parent = list(range(n + len(merges)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for s, (a, b, d, _) in enumerate(merges):
        if d <= threshold + 1e-12:
            parent[find(a)] = n + s
            parent[find(b)] = n + s
    roots = {}
    labels = []
    for i in range(n):
        r = find(i)
        if r not in roots:
            roots[r] = len(roots)
        labels.append(roots[r])
    return labels


def suggest_threshold(merges, tail=8):
    """在最後 tail 次合併中找最大的高度落差，取落差中點；少於 2 次合併時回傳 None。"""
    hs = [m[2] for m in merges]
    if len(hs) < 2:
        return None
    start = max(0, len(hs) - tail - 1)
    best_gap, best_mid = -1.0, None
    for i in range(start, len(hs) - 1):
        gap = hs[i + 1] - hs[i]
        if gap > best_gap:
            best_gap, best_mid = gap, (hs[i] + hs[i + 1]) / 2
    return best_mid
