"""
_mlp.py - 純標準庫的單隱藏層 MLP（tanh 隱藏層 + 線性輸出），含真實的反向傳播訓練（page13 skill_23 使用）

網路：  z_j = Σ_i W1[j][i]·x_i + b1[j]；  h_j = tanh(z_j)；  ŷ = Σ_j W2[j]·h_j + b2
損失：  L = (1/N) Σ (ŷ - t)²  （MSE，回報值不含權重衰減項）
反向傳播（鏈鎖律）：
  ∂L/∂ŷ  = 2(ŷ - t)/N
  ∂L/∂W2[j] = Σ ∂L/∂ŷ · h_j          ∂L/∂b2 = Σ ∂L/∂ŷ
  ∂L/∂z_j = ∂L/∂ŷ · W2[j] · (1 - h_j²)
  ∂L/∂W1[j][i] = Σ ∂L/∂z_j · x_i     ∂L/∂b1[j] = Σ ∂L/∂z_j
更新（全批次梯度下降）：w ← w - η(∂L/∂w + λ·w)，λ 為 L2 權重衰減（偏差項不衰減）。
"""

import math
import random


def init_weights(n_in: int, hidden: int, rng: random.Random) -> dict:
    s1 = math.sqrt(1.0 / n_in)
    s2 = math.sqrt(1.0 / hidden)
    return {
        "W1": [[rng.uniform(-s1, s1) for _ in range(n_in)] for _ in range(hidden)],
        "b1": [0.0] * hidden,
        "W2": [rng.uniform(-s2, s2) for _ in range(hidden)],
        "b2": 0.0,
    }


def forward(net: dict, x):
    """回傳 (預測值, 隱藏層輸出 h)。"""
    h = [math.tanh(sum(w * xi for w, xi in zip(row, x)) + b) for row, b in zip(net["W1"], net["b1"])]
    return sum(w * hj for w, hj in zip(net["W2"], h)) + net["b2"], h


def predict(net: dict, x) -> float:
    return forward(net, x)[0]


def mse(net: dict, X, y) -> float:
    return sum((forward(net, x)[0] - t) ** 2 for x, t in zip(X, y)) / len(X)


def gradients(net: dict, X, y):
    """全批次梯度（不含權重衰減）。回傳 (loss, dW1, db1, dW2, db2)。"""
    n = len(X)
    hid = len(net["W2"])
    dW1 = [[0.0] * len(X[0]) for _ in range(hid)]
    db1 = [0.0] * hid
    dW2 = [0.0] * hid
    db2 = 0.0
    loss = 0.0
    for x, t in zip(X, y):
        out, h = forward(net, x)
        e = out - t
        loss += e * e
        dy = 2.0 * e / n
        db2 += dy
        for j in range(hid):
            dW2[j] += dy * h[j]
            dz = dy * net["W2"][j] * (1.0 - h[j] * h[j])
            db1[j] += dz
            row = dW1[j]
            for i, xi in enumerate(x):
                row[i] += dz * xi
    return loss / n, dW1, db1, dW2, db2


def train(X, y, hidden=6, epochs=500, lr=0.05, weight_decay=0.001, seed=42):
    """全批次梯度下降。回傳 {net, loss_history（每個 epoch 的訓練 MSE，第 0 筆為訓練前）, diverged, convergence_epoch}。"""
    rng = random.Random(seed)
    net = init_weights(len(X[0]), hidden, rng)
    history = []
    diverged = False
    for ep in range(epochs + 1):
        loss, dW1, db1, dW2, db2 = gradients(net, X, y)
        history.append(loss)
        if not math.isfinite(loss) or (history[0] > 0 and loss > 100 * history[0] + 1e-9):
            diverged = True
            break
        if ep == epochs:
            break
        for j in range(hidden):
            net["b1"][j] -= lr * db1[j]
            net["W2"][j] -= lr * (dW2[j] + weight_decay * net["W2"][j])
            row = net["W1"][j]
            for i in range(len(row)):
                row[i] -= lr * (dW1[j][i] + weight_decay * row[i])
        net["b2"] -= lr * db2
    return {"net": net, "loss_history": history, "diverged": diverged,
            "convergence_epoch": convergence_epoch(history), "still_improving": still_improving(history)}


def convergence_epoch(history, window=20, rel_tol=0.002):
    """第一個「近 window 個 epoch 的損失下降比例 < rel_tol」的 epoch；一直沒有則回傳 None。"""
    for e in range(window, len(history)):
        prev = history[e - window]
        if prev > 0 and (prev - history[e]) / prev < rel_tol:
            return e
    return None


def still_improving(history, window=50, rel_tol=0.01):
    """最後 window 個 epoch 損失仍下降超過 rel_tol → 可能尚未收斂。"""
    if len(history) <= window:
        return True
    prev = history[-1 - window]
    return prev > 0 and (prev - history[-1]) / prev > rel_tol


def downsample(values, max_points=200):
    """等距抽樣，回傳 [(epoch, value)]，必含首尾。"""
    n = len(values)
    if n <= max_points:
        return [(i, values[i]) for i in range(n)]
    idx = sorted({round(i * (n - 1) / (max_points - 1)) for i in range(max_points)})
    return [(i, values[i]) for i in idx]
