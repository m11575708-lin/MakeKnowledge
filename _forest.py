"""
_forest.py - 純標準庫的 CART 決策樹與隨機森林（page10 使用；之後 page11 的 CART 可重用）

實作重點：
  * Gini 不純度  I_G(t) = 1 - Σ p_i²
  * 每個節點只在隨機抽到的 max_features 個特徵中找最佳切分（依 Gini 下降量最大）
  * 每棵樹用 Bootstrap（有放回）抽樣訓練；未被抽到的樣本為 OOB，用來估計泛化準確率
  * MDI（Mean Decrease Impurity）：
      每個內部節點 t 的貢獻 = (n_t/N)·I(t) - (n_l/N)·I(l) - (n_r/N)·I(r)，
      同一特徵加總後在單棵樹內歸一化，再對所有樹平均
  * 預測：每棵樹給出葉節點的不良比例（機率），森林取平均；多數決票數另外計算
"""

import math
import random

MAX_DEPTH = 6
MIN_LEAF = 5
MIN_SPLIT = 10


def gini(counts, n):
    if n == 0:
        return 0.0
    return 1.0 - sum((c / n) ** 2 for c in counts)


class _Node:
    __slots__ = ("feature", "threshold", "left", "right", "counts", "n", "impurity")

    def __init__(self, counts, n, impurity):
        self.feature = None
        self.threshold = None
        self.left = None
        self.right = None
        self.counts = counts
        self.n = n
        self.impurity = impurity


class DecisionTree:
    def __init__(self, n_features: int, n_classes: int = 2, max_depth: int = MAX_DEPTH,
                 min_leaf: int = MIN_LEAF, max_features: int = None, rng: random.Random = None):
        self.n_features = n_features
        self.n_classes = n_classes
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.max_features = max_features or n_features
        self.rng = rng or random.Random(0)
        self.root = None
        self.raw_importance = [0.0] * n_features
        self.n_train = 0

    def fit(self, X, y):
        self.n_train = len(X)
        self.root = self._grow(X, y, list(range(len(X))), 0)
        return self

    def _counts(self, y, idx):
        c = [0] * self.n_classes
        for i in idx:
            c[y[i]] += 1
        return c

    def _grow(self, X, y, idx, depth):
        n = len(idx)
        counts = self._counts(y, idx)
        node = _Node(counts, n, gini(counts, n))
        if depth >= self.max_depth or n < MIN_SPLIT or node.impurity == 0.0:
            return node
        feats = self.rng.sample(range(self.n_features), min(self.max_features, self.n_features))
        best = None   # (gain_weighted, feature, threshold, left_idx, right_idx)
        for f in feats:
            order = sorted(idx, key=lambda i: X[i][f])
            left = [0] * self.n_classes
            right = counts[:]
            for pos in range(n - 1):
                i = order[pos]
                left[y[i]] += 1
                right[y[i]] -= 1
                nl, nr = pos + 1, n - pos - 1
                if X[order[pos]][f] == X[order[pos + 1]][f]:
                    continue
                if nl < self.min_leaf or nr < self.min_leaf:
                    continue
                child = (nl * gini(left, nl) + nr * gini(right, nr)) / n
                gain = node.impurity - child
                if best is None or gain > best[0] + 1e-12:
                    thr = (X[order[pos]][f] + X[order[pos + 1]][f]) / 2.0
                    best = (gain, f, thr, nl, nr)
        if best is None or best[0] <= 1e-12:
            return node
        gain, f, thr, _, _ = best
        li = [i for i in idx if X[i][f] <= thr]
        ri = [i for i in idx if X[i][f] > thr]
        node.feature, node.threshold = f, thr
        # MDI：節點樣本占比 × Gini 下降量
        self.raw_importance[f] += (n / self.n_train) * gain
        node.left = self._grow(X, y, li, depth + 1)
        node.right = self._grow(X, y, ri, depth + 1)
        return node

    def _leaf(self, x):
        node = self.root
        while node.feature is not None:
            node = node.left if x[node.feature] <= node.threshold else node.right
        return node

    def predict_proba1(self, x) -> float:
        """葉節點中類別 1 的比例。"""
        leaf = self._leaf(x)
        return leaf.counts[1] / leaf.n if leaf.n else 0.0

    def predict(self, x) -> int:
        leaf = self._leaf(x)
        return 1 if leaf.counts[1] > leaf.counts[0] else 0

    def importance(self):
        s = sum(self.raw_importance)
        return [v / s for v in self.raw_importance] if s > 0 else [0.0] * self.n_features


class RandomForest:
    def __init__(self, n_trees: int = 100, seed: int = 7, max_depth: int = MAX_DEPTH,
                 min_leaf: int = MIN_LEAF, max_features: int = None):
        self.n_trees = n_trees
        self.seed = seed
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.max_features = max_features
        self.trees = []
        self.oob_accuracy = None
        self.oob_coverage = 0.0
        self.n_features = 0

    def fit(self, X, y):
        n, self.n_features = len(X), len(X[0])
        mf = self.max_features or max(1, int(round(math.sqrt(self.n_features))))
        master = random.Random(self.seed)
        oob_votes = [[0, 0] for _ in range(n)]
        self.trees = []
        for _ in range(self.n_trees):
            rng = random.Random(master.randrange(1 << 30))
            boot = [rng.randrange(n) for _ in range(n)]
            in_bag = set(boot)
            Xb, yb = [X[i] for i in boot], [y[i] for i in boot]
            tree = DecisionTree(self.n_features, 2, self.max_depth, self.min_leaf, mf, rng).fit(Xb, yb)
            self.trees.append(tree)
            for i in range(n):
                if i not in in_bag:
                    oob_votes[i][tree.predict(X[i])] += 1
        scored = [(v, y[i]) for i, v in enumerate(oob_votes) if v[0] + v[1] > 0]
        self.oob_coverage = len(scored) / n
        if scored:
            self.oob_accuracy = sum(1 for v, t in scored if (1 if v[1] > v[0] else 0) == t) / len(scored)
        return self

    def predict_detail(self, x):
        """回傳 (平均不良機率, 投不良的樹數, 樹數)。"""
        probs = [t.predict_proba1(x) for t in self.trees]
        votes = sum(t.predict(x) for t in self.trees)
        return sum(probs) / len(probs), votes, len(self.trees)

    def predict(self, x) -> int:
        _, votes, n = self.predict_detail(x)
        return 1 if votes > n / 2 else 0

    def mdi(self):
        imps = [t.importance() for t in self.trees]
        return [sum(col) / len(imps) for col in zip(*imps)]

    def accuracy(self, X, y) -> float:
        return sum(1 for xi, yi in zip(X, y) if self.predict(xi) == yi) / len(X)

    def permutation_importance(self, X, y, seed: int = 99, repeats: int = 5):
        """在（測試）資料上逐一打亂單一特徵，量測準確率下降量（重複 repeats 次取平均，降低隨機雜訊）。"""
        rng = random.Random(seed)
        base = self.accuracy(X, y)
        out = []
        for f in range(self.n_features):
            drops = []
            for _ in range(repeats):
                col = [row[f] for row in X]
                rng.shuffle(col)
                Xp = [row[:f] + [col[i]] + row[f + 1:] for i, row in enumerate(X)]
                drops.append(base - self.accuracy(Xp, y))
            out.append(sum(drops) / repeats)
        return out
