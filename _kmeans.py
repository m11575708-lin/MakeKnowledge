"""
_kmeans.py - 純標準庫的 K-Means、手肘判定與輪廓係數（page12 的 skill_20 / skill_21 共用）

K-Means（Lloyd 演算法）：
  1. 初始化：k-means++（第一個中心隨機，之後依「到最近中心距離²」的機率抽取，降低落入壞的起點）
  2. 指派：每個點歸到最近的中心（歐氏距離）
  3. 更新：μ_k = (1/|S_k|) Σ_{x∈S_k} x
  4. 重複 2–3 直到指派不再變動；空群會被重設到「離自己中心最遠的點」
  SSE = Σ_k Σ_{x∈S_k} ||x - μ_k||²（群內誤差平方和）
  因為結果依賴起點，每個 K 重跑 n_init 次，取 SSE 最小者（固定 seed，可重現）。

手肘判定（弦距法）：把 (k, SSE_k) 正規化到 [0,1]×[0,1]，找離「第一點到最後一點連線」最遠的 k。
輪廓係數：s(i) = (b-a)/max(a,b)，a=到同群其他點的平均距離、b=到最近其他群的平均距離；全體平均介於 -1~1，越大群結構越清楚。
"""

import math
import random

MAX_ROWS = 5000          # 純 Python 的效能上限
SIL_SAMPLE = 500         # 輪廓係數最多抽樣這麼多點


def sqdist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _kmeanspp(X, k, rng):
    centers = [X[rng.randrange(len(X))][:]]
    d2 = [sqdist(x, centers[0]) for x in X]
    while len(centers) < k:
        total = sum(d2)
        if total <= 0:                      # 所有點重合：任選
            centers.append(X[rng.randrange(len(X))][:])
        else:
            r, acc = rng.random() * total, 0.0
            pick = len(X) - 1
            for i, v in enumerate(d2):
                acc += v
                if acc >= r:
                    pick = i
                    break
            centers.append(X[pick][:])
        d2 = [min(d, sqdist(x, centers[-1])) for d, x in zip(d2, X)]
    return centers


def _assign(X, centers):
    labels, sse = [], 0.0
    for x in X:
        best, bd = 0, float("inf")
        for j, c in enumerate(centers):
            d = sqdist(x, c)
            if d < bd:
                best, bd = j, d
        labels.append(best)
        sse += bd
    return labels, sse


def kmeans_once(X, k, rng, max_iter=100):
    """回傳 (centers, labels, sse, n_iter, converged)。"""
    dim = len(X[0])
    centers = _kmeanspp(X, k, rng)
    labels = None
    converged = False
    it = 0
    for it in range(1, max_iter + 1):
        new, _ = _assign(X, centers)
        if new == labels:
            converged = True
            break
        labels = new
        sums = [[0.0] * dim for _ in range(k)]
        cnt = [0] * k
        for x, l in zip(X, labels):
            cnt[l] += 1
            for d in range(dim):
                sums[l][d] += x[d]
        for j in range(k):
            if cnt[j]:
                centers[j] = [s / cnt[j] for s in sums[j]]
            else:   # 空群：搬到離現有中心最遠的點
                far = max(range(len(X)), key=lambda i: sqdist(X[i], centers[labels[i]]))
                centers[j] = X[far][:]
    labels, sse = _assign(X, centers)
    return centers, labels, sse, it, converged


def kmeans(X, k, n_init=10, seed=42, max_iter=100):
    """多起點取最小 SSE，並把群依第一個座標由小到大重新編號（讓編號穩定）。"""
    rng = random.Random(seed)
    best = None
    all_converged = True
    for _ in range(n_init):
        res = kmeans_once(X, k, rng, max_iter)
        all_converged = all_converged and res[4]
        if best is None or res[2] < best[2] - 1e-12:
            best = res
    centers, labels, sse, it, conv = best
    order = sorted(range(k), key=lambda j: centers[j][0])
    remap = {old: new for new, old in enumerate(order)}
    return {"centers": [centers[j] for j in order], "labels": [remap[l] for l in labels], "sse": sse,
            "n_iter": it, "converged": conv, "all_inits_converged": all_converged, "n_init": n_init}


def elbow_index(ks, sses):
    """弦距法。回傳 (最佳 k, 強度 0~1, 各 k 的弦距)。SSE 全相同時回傳 (None, 0, [])。"""
    s_max, s_min = sses[0], sses[-1]
    if len(ks) < 3 or s_max - s_min <= 1e-12:
        return None, 0.0, []
    dists = []
    for i, (k, s) in enumerate(zip(ks, sses)):
        x = i / (len(ks) - 1)
        y = (s - s_min) / (s_max - s_min)
        dists.append((1 - x - y) / math.sqrt(2))
    best = max(range(len(ks)), key=lambda i: dists[i])
    return ks[best], dists[best] * math.sqrt(2), dists


def silhouette(X, labels, k, seed=1):
    """平均輪廓係數（點數超過 SIL_SAMPLE 時固定 seed 抽樣）。k<2 或任一群只有 1 點時回傳 None。"""
    n = len(X)
    idx = list(range(n))
    if n > SIL_SAMPLE:
        idx = random.Random(seed).sample(idx, SIL_SAMPLE)
    groups = {j: [i for i in idx if labels[i] == j] for j in range(k)}
    if k < 2 or sum(1 for g in groups.values() if g) < 2:
        return None
    total, cnt = 0.0, 0
    for i in idx:
        own = labels[i]
        if len(groups[own]) < 2:
            continue                                  # 單點群的 s 定義為 0，這裡略過
        a = sum(math.sqrt(sqdist(X[i], X[o])) for o in groups[own] if o != i) / (len(groups[own]) - 1)
        b = min(sum(math.sqrt(sqdist(X[i], X[o])) for o in g) / len(g)
                for j, g in groups.items() if j != own and g)
        total += (b - a) / max(a, b) if max(a, b) > 0 else 0.0
        cnt += 1
    return total / cnt if cnt else None
