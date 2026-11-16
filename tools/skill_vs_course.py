"""skill_vs_course.py — 用 course_ref.py（依講義公式自行實作、已通過講義例題檢查）重算各 Skill 的數字並比對。

用法（在專案根目錄）：python tools/skill_vs_course.py
每一列：Skill、項目、Skill 的值、對照程式的值、結果（一致／有差異）、說明。
只用 Python 標準函式庫；直接呼叫各 Skill 自己的資料與切分，確保兩邊吃的是同一份資料。
"""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "skills"), os.path.join(ROOT, "tools")]

import course_ref as C  # noqa: E402

ROWS = []


def row(skill, item, skill_val, ref_val, tol, note=""):
    same = abs(skill_val - ref_val) <= tol if isinstance(skill_val, (int, float)) else skill_val == ref_val
    ROWS.append((skill, item, skill_val, ref_val, "一致" if same else "有差異", note))


def r6(v):
    return round(v, 6) if isinstance(v, float) else v


# ---------------------------------------------------------------- skill_04：多元線性迴歸
def check_rul():
    import skill_04_equipment_rul_prediction as s4
    from skill_03_sensor_data_preprocessing import FEATURES, load_reference_dataset
    m = s4.fit_rul_model()
    rows, _ = load_reference_dataset()
    idx = list(range(len(rows)))
    random.Random(s4.SPLIT_SEED).shuffle(idx)
    n_test = max(1, int(len(rows) * s4.TEST_RATIO))
    test, train = [rows[i] for i in idx[:n_test]], [rows[i] for i in idx[n_test:]]
    beta = C.multi([[r[f] for f in FEATURES] for r in train], [r["rul_hours"] for r in train])
    row("skill_04", "截距（原始單位）", r6(m["raw_intercept"]), r6(beta[0]), 1e-6)
    for i, f in enumerate(FEATURES):
        row("skill_04", f"係數 {f}", r6(m["raw_coefs"][f]), r6(beta[i + 1]), 1e-6)
    mt = C.metrics([r["rul_hours"] for r in test], C.predict_multi(beta, [[r[f] for f in FEATURES] for r in test]))
    row("skill_04", "測試 MAE", r6(m["metrics"]["mae"]), r6(mt["mae"]), 1e-6)
    row("skill_04", "測試 RMSE", r6(m["metrics"]["rmse"]), r6(mt["rmse"]), 1e-6)
    row("skill_04", "測試 R²", r6(m["metrics"]["r2"]), r6(mt["r2"]), 1e-6)


# ---------------------------------------------------------------- skill_06、08：邏輯迴歸與門檻成本
def check_failure():
    import _failure_model as fm
    import skill_08_cost_sensitive_threshold_tuning as s8
    m = fm.fit_failure_model()
    rows, _ = fm.load_reference_dataset()
    idx = list(range(len(rows)))
    random.Random(fm.SPLIT_SEED).shuffle(idx)
    n_test = max(1, int(len(rows) * fm.TEST_RATIO))
    test, train = [rows[i] for i in idx[:n_test]], [rows[i] for i in idx[n_test:]]
    w = C.logit_mle([[r[f] for f in fm.FEATURES] for r in train], [r["failed"] for r in train])
    note = "Skill 加了 L2 正則化 λ＝0.001，講義沒有，係數會差一點"
    row("skill_06", "截距（原始單位）", r6(m["raw_intercept"]), r6(w[0]), 0.01, note)
    for i, f in enumerate(fm.FEATURES):
        row("skill_06", f"係數 {f}", r6(m["raw_coefs"][f]), r6(w[i + 1]), 0.01, note)
    p_ref = [C.sigmoid(w[0] + sum(w[i + 1] * r[f] for i, f in enumerate(fm.FEATURES))) for r in test]
    y = [r["failed"] for r in test]
    acc_ref = sum((1 if p >= 0.5 else 0) == t for p, t in zip(p_ref, y)) / len(y)
    row("skill_06", "測試準確率（門檻 0.5）", r6(m["metrics"]["accuracy"]), r6(acc_ref), 1e-9)
    tp, fp, fn, tn = C.confusion(m["test_labels"], m["test_probs"], 0.5)
    row("skill_06", "門檻 0.5 的混淆矩陣 TP/FP/FN/TN", None, (tp, fp, fn, tn), 0,
        "Skill 不輸出這一項，列出供參考")
    ROWS[-1] = ROWS[-1][:2] + ("—", f"{tp}/{fp}/{fn}/{tn}", "參考", ROWS[-1][5])

    # 門檻成本：Skill 用 C停機×FN ＋ C檢修×FP；講義用 每張警示×成本 ＋ 漏掉×成本（警示含 TP）
    c_down, c_insp = 50000.0, 2000.0
    res = s8.tune_cost_threshold(cost_downtime=c_down, cost_inspection=c_insp)
    probs, labels = m["test_probs"], m["test_labels"]
    thetas = [round(i * 0.01, 2) for i in range(101)]
    skill_style = min(thetas, key=lambda t: (C.confusion(labels, probs, t)[1] * c_insp + C.confusion(labels, probs, t)[2] * c_down, t))
    s_cost = C.confusion(labels, probs, skill_style)[1] * c_insp + C.confusion(labels, probs, skill_style)[2] * c_down
    row("skill_08", "最佳門檻（Skill 的成本定義重算）", res["optimal_threshold"], skill_style, 1e-9)
    row("skill_08", "最低總成本（Skill 的成本定義重算）", res["total_cost_min"], s_cost, 1e-6)
    lec = min(thetas, key=lambda t: (C.cost(labels, probs, t, c_insp, c_down), t))
    row("skill_08", "最佳門檻（講義的成本定義）", res["optimal_threshold"], lec, 1e-9,
        "講義把每一張警示（含真的會壞的 TP）都算檢修費；Skill 只算誤報（FP）的檢修費")
    row("skill_08", "最低總成本（講義的成本定義）", res["total_cost_min"], C.cost(labels, probs, lec, c_insp, c_down), 1e-6,
        "同上：定義不同，總成本不能直接比")


# ---------------------------------------------------------------- skill_09：K 近鄰
def check_knn():
    import skill_09_similar_repair_case_search as s9
    from _repair_data import load_case_base
    import skill_10_error_code_feature_matching as s10
    # 與 08 頁相同的呼叫順序：skill_10 先算特徵權重，再交給 skill_09（權重倍率用頁面預設 1）
    pat = s10.match_error_code_pattern(error_code="E-8021", feature_vector=[2.8, 75.0, 1.8])
    res = s9.search_similar_repair_cases(feature_vector=[2.8, 75.0, 1.8], top_k=3, weights=pat["feature_weights"],
                                         error_code="E-8021")
    cases = load_case_base()["cases"]
    p = len(res["feature_vector"])
    stats = s9.feature_stats(cases)
    w = res["weights"]
    zq = [(res["feature_vector"][i] - stats[i]["mean"]) / stats[i]["std"] for i in range(p)]
    for c in res["top3_similar_cases"]:
        zc = [(c["features"][i] - stats[i]["mean"]) / stats[i]["std"] for i in range(p)]
        # 講義的歐氏距離 √Σ(差²)；Skill 每一維先乘權重 wᵢ，再除以維度數 p 取平均
        d_ref = C.euclid([math.sqrt(w[i]) * zq[i] for i in range(p)], [math.sqrt(w[i]) * zc[i] for i in range(p)]) / math.sqrt(p)
        row("skill_09", f"{c['case_id']} 距離", r6(c["distance"]), round(d_ref, 4), 1e-4,
            "講義的歐氏距離，加上 Skill 的特徵權重並除以 √維度數（Skill 的設計）")


# ---------------------------------------------------------------- skill_11：物品協同過濾
def check_cf():
    import skill_11_spare_parts_recommendation as s11
    from _repair_data import load_case_base
    base = load_case_base()
    res = s11.recommend_spare_parts(neighbors=[{"case_id": "MA-2024-089", "similarity": 1.0},
                                               {"case_id": "MA-2024-117", "similarity": 0.8407},
                                               {"case_id": "MA-2024-102", "similarity": 0.8096}])
    # 把「案例 × 備品」的 0／1 領用當成講義的評分表（沒領用＝0），用講義的餘弦算備品相似度
    ratings = {c["case_id"]: {p: 1 for p in c["parts_used"]} for c in base["cases"]}
    items = sorted({p for c in base["cases"] for p in c["parts_used"]})
    users = list(ratings)
    col = {i: [ratings[u].get(i, 0) for u in users] for i in items}
    nrm = {i: math.sqrt(sum(v * v for v in col[i])) for i in items}
    def sim(a, b):
        return sum(x * y for x, y in zip(col[a], col[b])) / (nrm[a] * nrm[b])
    a, b = "SP-8821", "SP-8822"
    co = len({c["case_id"] for c in base["cases"] if a in c["parts_used"]} & {c["case_id"] for c in base["cases"] if b in c["parts_used"]})
    n_a = sum(1 for c in base["cases"] if a in c["parts_used"]); n_b = sum(1 for c in base["cases"] if b in c["parts_used"])
    row("skill_11", f"相似度 {a}–{b}", r6(co / math.sqrt(n_a * n_b)), r6(sim(a, b)), 1e-9,
        "Skill 的「共現次數 ÷ √(nᵢnⱼ)」就是講義 0／1 評分表上的餘弦相似度")
    top = res["recommended_parts"][0]
    row("skill_11", "推薦分數的算法", "Σ 輪廓×相似度 ÷ Σ 輪廓（全部已用備品）", "Σ 相似度×分數 ÷ Σ 相似度（最像的 k 個）", 0,
        f"刻意不同：備品是 0／1 領用，套講義公式每個預測都是 1；Skill 首選 {top['part_id']} {top['score']}")
    ROWS[-1] = ROWS[-1][:4] + ("算法不同", ROWS[-1][5])


# ---------------------------------------------------------------- skill_13：感知器
def check_perceptron():
    import skill_13_error_code_perceptron_check as s13
    st = s13.build_state()
    rows, _ = s13.load_reference_dataset()
    idx = list(range(len(rows)))
    random.Random(s13.SPLIT_SEED).shuffle(idx)
    n_test = max(1, int(len(rows) * s13.TEST_RATIO))
    train = [rows[i] for i in idx[n_test:]]
    order = list(range(len(train)))
    random.Random(s13.SPLIT_SEED + 1).shuffle(order)
    train = [train[i] for i in order]
    Z = [[(r[f] - st["mean"][k]) / st["std"][k] for k, f in enumerate(s13.FEATURES)] for r in train]
    w, b, ep, errs = C.perceptron(Z, [r["label"] for r in train], eta=s13.ETA)
    row("skill_13", "w1", r6(st["w"][0]), r6(w[0]), 1e-9); row("skill_13", "w2", r6(st["w"][1]), r6(w[1]), 1e-9)
    row("skill_13", "b", r6(st["b"]), r6(b), 1e-9)
    row("skill_13", "收斂輪數", st["metrics"]["epochs"], ep, 0)
    row("skill_13", "訓練時判錯總數", st["metrics"]["train_mistakes"], sum(errs), 0)


# ---------------------------------------------------------------- skill_17：CART 決策樹（根節點）
def check_tree():
    import _steel_model as sm
    m = sm.get_model()
    root = m["tree"]
    best = None
    for j, f in enumerate(sm.FEATURES):
        t, g = C.best_numeric_split([x[j] for x in m["Xtr"]], m["ytr"], crit=C.gini)
        if best is None or g > best[2] + 1e-12:
            best = (f, t, g)
    row("skill_17", "根節點欄位", sm.FEATURES[root["feature"]], best[0], 0)
    row("skill_17", "根節點切點", r6(root["threshold"]), r6(best[1]), 1e-9, "講義：相鄰兩值的中點")
    row("skill_17", "根節點吉尼下降", r6(root["gain"]), r6(best[2]), 1e-9)


# ---------------------------------------------------------------- skill_20、21：K 平均
def check_kmeans():
    import _spc_data as sd
    import _kmeans as km
    rows, _ = sd.load_data()[:2] if isinstance(sd.load_data(), tuple) else (sd.load_data(), None)
    cols = ["temp", "pressure"]
    Z, _ = sd.standardize(rows if isinstance(rows, list) else rows["rows"], cols)
    res = km.kmeans(Z, 3, n_init=10, seed=42)
    # 對照：用 Skill 找到的中心當講義 kmeans 的起點，跑到沒人換群，SSE 應相同
    cen, asg, sse, rnd = C.kmeans(Z, [c[:] for c in res["centers"]])
    row("skill_20", "k＝3 的 SSE（以 Skill 中心為起點重跑）", r6(res["sse"]), r6(sse), 1e-6)
    # 對照：200 組隨機起點的最小 SSE（Skill 只試 10 組）
    rng = random.Random(0)
    best = min(C.kmeans(Z, [Z[i][:] for i in rng.sample(range(len(Z)), 3)])[2] for _ in range(200))
    row("skill_21", "k＝3 的最小 SSE（對照試 200 組起點）", r6(res["sse"]), r6(best), 1e-6,
        "K 平均只保證局部最小；兩邊一樣表示 Skill 的 10 組起點已找到同一個最小值")
    n = len(Z)
    row("skill_21", "k＝1 的 SSE", r6(km.kmeans(Z, 1)["sse"]), float(2 * (n - 1)), 1e-6,
        f"Skill 用樣本標準差（÷ n−1），所以 k＝1 是 2×(n−1)＝{2 * (n - 1)}；講義用母體標準差會是 2n＝{2 * n}")


# ---------------------------------------------------------------- skill_22：SPC
def check_spc():
    import skill_22_spc_control_limit_monitoring as s22
    series = [0.12, -0.45, 1.2, 0.35, -0.3, 0.3, -0.8, 0.5, 0.1, -0.2, 0.6, -0.4, 0.25, 0.0, -0.6, 0.45, 0.2, -0.1, 0.7, 4.5]
    res = s22.monitor_spc(data_series=series)
    mu = sum(series) / len(series)
    sd = math.sqrt(sum((v - mu) ** 2 for v in series) / (len(series) - 1))
    row("skill_22", "UCL（20 點小例子手算）", r6(res["spc_limits"]["ucl"]), r6(mu + 3 * sd), 1e-4, "課堂沒有教 SPC，用定義手算")
    row("skill_22", "LCL（20 點小例子手算）", r6(res["spc_limits"]["lcl"]), r6(mu - 3 * sd), 1e-4)
    row("skill_22", "超界點數", res["outliers_count"], sum(1 for v in series if v > mu + 3 * sd or v < mu - 3 * sd), 0)


# ---------------------------------------------------------------- skill_23：MLP 反向傳播
def check_mlp():
    import _mlp
    rng = random.Random(7)
    net = _mlp.init_weights(3, 4, rng)
    X = [[rng.uniform(-1, 1) for _ in range(3)] for _ in range(6)]
    y = [rng.uniform(-1, 1) for _ in range(6)]
    loss, dW1, db1, dW2, db2 = _mlp.gradients(net, X, y)
    def num_grad(path):
        eps = 1e-6
        def get(n):
            o = n
            for p in path[:-1]:
                o = o[p]
            return o
        o = get(net); k = path[-1]
        old = o[k]; o[k] = old + eps; lp = _mlp.mse(net, X, y); o[k] = old - eps; lm = _mlp.mse(net, X, y); o[k] = old
        return (lp - lm) / (2 * eps)
    row("skill_23", "∂L/∂W1[0][0] 解析 vs 數值微分", r6(dW1[0][0]), r6(num_grad(["W1", 0, 0])), 1e-6,
        "講義的盆栽網路用 sigmoid 輸出與 ½(ŷ−y)²；Skill 是 tanh 隱藏層、線性輸出、MSE（預測數值用），所以改用數值微分驗證鏈鎖律")
    row("skill_23", "∂L/∂W2[2] 解析 vs 數值微分", r6(dW2[2]), r6(num_grad(["W2", 2])), 1e-6)
    row("skill_23", "∂L/∂b1[1] 解析 vs 數值微分", r6(db1[1]), r6(num_grad(["b1", 1])), 1e-6)


# ---------------------------------------------------------------- skill_24、25：階層式分群
def check_hier():
    import _equipment_data as ed
    import _hier
    data = ed.load_data()
    rows = data["rows"] if isinstance(data, dict) else data[0]
    ind = data.get("indicators") if isinstance(data, dict) else ["failure_rate", "mtbf_hours", "load_pct"]
    Z, _ = ed.risk_matrix(rows, ind)
    sk = _hier.agglomerate(Z, "average")
    sk_heights = [m[2] for m in sk["merge_history"]]
    ref = C.hier(Z, "average")
    same = [round(h, 9) for h in sk_heights] == [round(h, 9) for _, _, h in ref]
    ROWS.append(("skill_24", f"{len(Z)} 台的 {len(ref)} 次合併高度（average）",
                 "最後 3 步 " + "、".join(f"{h:.4f}" for h in sk_heights[-3:]),
                 "最後 3 步 " + "、".join(f"{h:.4f}" for _, _, h in ref[-3:]), "一致" if same else "有差異",
                 "全部合併高度逐一比對" + ("相同" if same else "不同")))
    for link in ("single", "complete"):
        a = [round(m[2], 9) for m in _hier.agglomerate(Z, link)["merge_history"]]
        b = [round(h, 9) for _, _, h in C.hier(Z, link)]
        ROWS.append(("skill_24", f"合併高度（{link}）", f"最後一步 {a[-1]:.4f}", f"最後一步 {b[-1]:.4f}",
                     "一致" if a == b else "有差異", "全部合併高度逐一比對" + ("相同" if a == b else "不同")))


def main():
    for fn in (check_rul, check_failure, check_knn, check_cf, check_perceptron, check_tree, check_kmeans, check_spc,
               check_mlp, check_hier):
        try:
            fn()
        except Exception as e:  # 一項失敗不影響其他項，錯誤照實列出
            ROWS.append((fn.__name__, "執行錯誤", "—", "—", "錯誤", repr(e)[:160]))
    w = max(len(r[1]) for r in ROWS)
    for r in ROWS:
        print(f"{r[4]:4s} {r[0]:9s} {r[1]:{w}s}  Skill {str(r[2]):<22} 對照 {str(r[3]):<22} {r[5]}")
    bad = [r for r in ROWS if r[4] in ("有差異", "錯誤")]
    print(f"\n共 {len(ROWS)} 項；有差異或錯誤 {len(bad)} 項（各項說明見右欄）")


if __name__ == "__main__":
    main()
