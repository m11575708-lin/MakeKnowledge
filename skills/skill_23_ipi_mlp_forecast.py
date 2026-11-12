"""
skill_23_ipi_mlp_forecast.py - 工業生產指數（IPI）多層類神經網路預測技能（真實訓練）

對應系統規格：US-14 / 13. 智慧生產指數預測與管理頁
演算法機制：輸入驗證與特徵建構 -> 時間切分與標準化 -> 前向傳播 -> 反向傳播訓練（梯度下降）
            -> 測試期誤差對照「延續上月」基準 + Guardrail

說明（請務必讀）：
  * 這是真的在訓練：單隱藏層 MLP（tanh 隱藏層、線性輸出），全批次梯度下降，鏈鎖律反向傳播，
    Δw = -η(∂L/∂w + λw)。梯度已用數值微分驗證（誤差 < 1e-9）。
  * 直接多步預測：對未來第 1、2、3 個月（= 下一季）各訓練一個網路，預測「變化量」IPI(t+h) − IPI(t)。
    這樣不需要未來的出口訂單與稼動率，也避開 MLP 對長期趨勢外推能力差的問題；「延續上月」基準 = 預測變化量為 0。
  * 時間切分（不是隨機切分）：前 80% 的時間為訓練期、後 20% 為測試期；
    目標落在測試期的訓練樣本會被剔除（purge），避免未來資訊洩漏進訓練。
    標準化的平均與標準差只用訓練樣本計算。
  * 測試期 RMSE 與基準比較：沒有勝過「延續上月」就明說（不是所有時間序列都值得用 MLP）。
  * 預測值之後再用「全部資料重新訓練」的網路產生（同樣 epoch、同樣超參數；誤差指標仍來自訓練期模型）。
  * 區間 = 預測 ± 1.96 × 該期測試 RMSE，是粗略的經驗區間，不是嚴格的信賴區間。
  * 輸出一律標示「僅供參考」。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from . import _mlp as mlp
    from . import _ipi_data as ds
except ImportError:
    from _common import StepLog, default_output_path, save_json
    import _mlp as mlp
    import _ipi_data as ds

SKILL_NAME = "skill_23_ipi_mlp_forecast"
TEST_FRACTION = 0.2
MIN_TRAIN = 30
MIN_TEST = 10
EPOCH_RANGE = (10, 5000)
HIDDEN_RANGE = (2, 32)
LR_MAX = 1.0
EXTRAP_Z = 3.0
OVERFIT_RATIO = 2.0
DISCLAIMER = "預測結果僅供參考，不應作為生產排程或投資的唯一依據"

PLAN = [
    ("輸入驗證與特徵建構", "Boundary & Type Validation + Feature Engineering (Δ, season dummies)", "math"),
    ("時間切分與標準化（僅用訓練期統計量）", "Chronological Train/Test Split + Z-Score (train stats only)", "math"),
    ("前向傳播（tanh 隱藏層）", "MLP Forward Propagation  ŷ = W₂·tanh(W₁x + b₁) + b₂", "math"),
    ("反向傳播與梯度下降訓練", "Backpropagation (Chain Rule)  Δw = -η ∂L/∂w", "random, math"),
    ("測試誤差對照基準與 Guardrail 檢核", "RMSE vs Persistence Baseline + Threshold-based Guardrail", "Python Control Flow"),
]


def _mean_std(vals):
    m = sum(vals) / len(vals)
    s = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0.0
    return m, s


def _check_series(name, v, n=None):
    if not isinstance(v, (list, tuple)) or not v:
        return None, f"{name} 必須是非空的數值陣列"
    if len(v) > ds.MAX_MONTHS:
        return None, f"{name} 共 {len(v)} 筆，超過上限 {ds.MAX_MONTHS}"
    out = []
    for i, x in enumerate(v):
        c = ds.clean_num(x)
        if c is None:
            return None, f"{name} 第 {i + 1} 個值不是有限數值"
        out.append(c)
    if n is not None and len(out) != n:
        return None, f"{name} 長度 {len(out)} 與 historical_ipi 的 {n} 不一致"
    return out, None


def forecast_ipi_mlp(historical_ipi=None, export_orders=None, utilization=None, start_month=None, features=None,
                     epochs: int = 500, learning_rate: float = 0.05, hidden_units: int = 6, seed: int = 42,
                     weight_decay: float = 0.001, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("ipi_forecast_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    source = "使用者提供的序列"

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        result["disclaimer"] = DISCLAIMER
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "ipi_forecast_next_quarter": [],
                       "training_loss_final": None, "loss_history": [], "test_rmse": None, "baseline_rmse": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # ---- 1. 驗證與特徵 ----
    errors = []
    if historical_ipi is None:
        rows, source = ds.load_data()
        historical_ipi = [r["ipi"] for r in rows]
        export_orders = [r["export_orders"] for r in rows] if export_orders is None else export_orders
        utilization = [r["utilization"] for r in rows] if utilization is None else utilization
        if start_month is None:
            start_month = int(rows[0]["month"].split("-")[1])
    ipi, e = _check_series("historical_ipi", historical_ipi)
    if e:
        errors.append(e)
    n = len(ipi) if ipi else None
    if ipi:
        if n < ds.MIN_MONTHS:
            errors.append(f"只有 {n} 個月，至少需要 {ds.MIN_MONTHS} 個月才能切出訓練與測試期")
        if any(not ds.MIN_IPI <= v <= ds.MAX_IPI for v in ipi):
            errors.append(f"IPI 需介於 [{ds.MIN_IPI:g}, {ds.MAX_IPI:g}]")
    exp = util = None
    if ipi:
        if export_orders is not None:
            exp, e = _check_series("export_orders", export_orders, n)
            errors += [e] if e else []
        if utilization is not None:
            util, e = _check_series("utilization", utilization, n)
            errors += [e] if e else []
    if start_month is None:
        start_month = 1
    if isinstance(start_month, bool) or not isinstance(start_month, int) or not 1 <= start_month <= 12:
        errors.append("start_month 必須是 1–12 的整數（第一筆資料的日曆月份）")
    available = ["ipi", "season"] + (["export"] if exp is not None else []) + (["util"] if util is not None else [])
    if features is None:
        feats = [k for k in ds.FEATURE_KEYS if k in available]
    elif not isinstance(features, (list, tuple)) or not features or any(f not in ds.FEATURE_KEYS for f in features):
        feats = []
        errors.append(f"features 必須是 {ds.FEATURE_KEYS} 的非空子集合")
    else:
        feats = [k for k in ds.FEATURE_KEYS if k in features]
        miss = [ds.FEATURE_LABELS[f] for f in feats if f not in available]
        if miss:
            errors.append(f"缺少特徵所需的資料：{'、'.join(miss)}")
    if isinstance(epochs, bool) or not isinstance(epochs, int) or not EPOCH_RANGE[0] <= epochs <= EPOCH_RANGE[1]:
        errors.append(f"epochs 需為 {EPOCH_RANGE[0]}–{EPOCH_RANGE[1]} 的整數")
    if isinstance(hidden_units, bool) or not isinstance(hidden_units, int) or not HIDDEN_RANGE[0] <= hidden_units <= HIDDEN_RANGE[1]:
        errors.append(f"hidden_units 需為 {HIDDEN_RANGE[0]}–{HIDDEN_RANGE[1]} 的整數")
    lr = ds.clean_num(learning_rate)
    if lr is None or not 0 < lr <= LR_MAX:
        errors.append(f"learning_rate 需為 (0, {LR_MAX:g}] 的數值")
    wd = ds.clean_num(weight_decay)
    if wd is None or not 0 <= wd <= 0.1:
        errors.append("weight_decay 需為 [0, 0.1] 的數值")
    if isinstance(seed, bool) or not isinstance(seed, int):
        errors.append("seed 必須為整數")
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)

    names = ds.feature_names(feats)
    log.add(f"資料 {n} 個月（{source}），首月為 {start_month} 月；使用特徵 {len(names)} 欄：{'、'.join(names)}；"
            f"對 h = 1、2、3（未來三個月）各建一個樣本集，目標為變化量 IPI(t+h) − IPI(t)。")

    # ---- 2. 時間切分與標準化 ----
    split = int(n * (1 - TEST_FRACTION))
    per_h = {}
    for h in ds.HORIZONS:
        ts, X, y = ds.build_samples(ipi, exp, util, start_month, feats, h)
        tr = [i for i, t in enumerate(ts) if t + h < split]
        te = [i for i, t in enumerate(ts) if t >= split]
        per_h[h] = {"ts": ts, "X": X, "y": y, "tr": tr, "te": te}
    h1 = per_h[1]
    if len(h1["tr"]) < MIN_TRAIN or len(h1["te"]) < MIN_TEST:
        log.add(f"訓練樣本 {len(h1['tr'])}、測試樣本 {len(h1['te'])}，低於下限（{MIN_TRAIN} / {MIN_TEST}），無法可靠評估。")
        return blocked("樣本不足", "BLOCKED_BY_GUARDRAIL (not enough samples)",
                       f"訓練樣本 {len(h1['tr'])} 筆、測試樣本 {len(h1['te'])} 筆，低於下限（{MIN_TRAIN} / {MIN_TEST}），請提供更長的歷史資料")
    prep = {}
    for h in ds.HORIZONS:
        d = per_h[h]
        Xtr = [d["X"][i] for i in d["tr"]]
        ytr = [d["y"][i] for i in d["tr"]]
        stats = [_mean_std(col) for col in zip(*Xtr)]
        ym, ys = _mean_std(ytr)
        if ys <= 1e-12:
            log.add(f"h={h} 的訓練目標沒有變異（標準差 0），無法訓練。")
            return blocked("目標無變異", "BLOCKED_BY_GUARDRAIL (no variance)", "IPI 變化量完全沒有變異，無法訓練預測模型")
        prep[h] = {"stats": [(m, s if s > 1e-12 else 1.0) for m, s in stats], "ym": ym, "ys": ys}
    log.add(f"以第 {split} 個月為界做時間切分（前 {split} 個月為訓練期、後 {n - split} 個月為測試期）；"
            f"h=1 訓練樣本 {len(h1['tr'])}、測試樣本 {len(h1['te'])}（目標落在測試期的訓練樣本已剔除）；"
            f"特徵與目標的平均、標準差只用訓練樣本計算，測試資料不參與。")

    def z(h, x):
        return [(v - m) / s for v, (m, s) in zip(x, prep[h]["stats"])]

    # ---- 3. 前向傳播（訓練前） ----
    init_losses = {}
    nets_init = {}
    import random as _r
    for h in ds.HORIZONS:
        d = per_h[h]
        Xz = [z(h, d["X"][i]) for i in d["tr"]]
        yz = [(d["y"][i] - prep[h]["ym"]) / prep[h]["ys"] for i in d["tr"]]
        net0 = mlp.init_weights(len(Xz[0]), hidden_units, _r.Random(seed + h))
        init_losses[h] = mlp.mse(net0, Xz, yz)
    n_params = hidden_units * len(names) + hidden_units + hidden_units + 1
    log.add(f"網路結構：輸入 {len(names)} → 隱藏 {hidden_units}（tanh）→ 輸出 1（線性），每個網路 {n_params} 個參數、共 3 個網路；"
            f"ŷ = Σ W₂ⱼ·tanh(Σ W₁ⱼᵢxᵢ + b₁ⱼ) + b₂。隨機初始權重（seed={seed}）的訓練 MSE（標準化單位）："
            + "、".join(f"h={h}: {init_losses[h]:.3f}" for h in ds.HORIZONS) + "。")

    # ---- 4. 反向傳播訓練 ----
    trained = {}
    diverged = []
    for h in ds.HORIZONS:
        d = per_h[h]
        Xz = [z(h, d["X"][i]) for i in d["tr"]]
        yz = [(d["y"][i] - prep[h]["ym"]) / prep[h]["ys"] for i in d["tr"]]
        r = mlp.train(Xz, yz, hidden_units, epochs, lr, wd, seed + h)
        trained[h] = r
        if r["diverged"]:
            diverged.append(h)
    if diverged:
        log.add(f"h={diverged} 的訓練發散（損失變成無限大或超過起始值 100 倍），學習率 {lr:g} 過大。")
        return blocked("訓練發散", "BLOCKED_BY_GUARDRAIL (training diverged)",
                       f"學習率 {lr:g} 過大，訓練發散；請調小學習率（建議 0.01–0.1）")
    hist1 = trained[1]["loss_history"]
    log.add(f"全批次梯度下降 {epochs} 個 epoch、學習率 η={lr:g}、L2 權重衰減 λ={wd:g}；每個 epoch 先前向算損失，再用鏈鎖律反向傳播求梯度並更新 "
            f"w ← w − η(∂L/∂w + λw)。h=1 的訓練 MSE 由 {hist1[0]:.3f} 降到 {hist1[-1]:.3f}"
            + f"（約第 {trained[1]['convergence_epoch']} epoch 起每 20 epoch 改善 < 0.2%）" if trained[1]['convergence_epoch'] is not None
            else f"全批次梯度下降 {epochs} 個 epoch、學習率 η={lr:g}、L2 權重衰減 λ={wd:g}；反向傳播更新 w ← w − η(∂L/∂w + λw)。"
                 f"h=1 的訓練 MSE 由 {hist1[0]:.3f} 降到 {hist1[-1]:.3f}（尚未達到收斂判準）。")

    # ---- 5. 評估 + 預測 + Guardrail ----
    horizons_out = []
    se_model_all = se_base_all = cnt_all = 0
    test_pred_h1 = []
    for h in ds.HORIZONS:
        d, p = per_h[h], prep[h]
        net = trained[h]["net"]

        def pred_delta(x):
            return mlp.predict(net, z(h, x)) * p["ys"] + p["ym"]

        te_err = [(pred_delta(d["X"][i]) - d["y"][i]) for i in d["te"]]
        te_base = [d["y"][i] for i in d["te"]]            # 基準預測變化量為 0 → 誤差 = −y
        tr_err = [(pred_delta(d["X"][i]) - d["y"][i]) for i in d["tr"]]
        rm = math.sqrt(sum(v * v for v in te_err) / len(te_err))
        rb = math.sqrt(sum(v * v for v in te_base) / len(te_base))
        rt = math.sqrt(sum(v * v for v in tr_err) / len(tr_err))
        rb_tr = math.sqrt(sum(d["y"][i] ** 2 for i in d["tr"]) / len(d["tr"]))
        se_model_all += sum(v * v for v in te_err)
        se_base_all += sum(v * v for v in te_base)
        cnt_all += len(te_err)
        horizons_out.append({"h": h, "train_rmse": round(rt, 4), "train_baseline_rmse": round(rb_tr, 4), "test_rmse": round(rm, 4),
                             "baseline_rmse": round(rb, 4), "beats_baseline": rm < rb, "n_train": len(d["tr"]), "n_test": len(d["te"]),
                             "improvement_pct": round((1 - rm / rb) * 100, 1) if rb > 0 else None,
                             "training_loss_final": round(trained[h]["loss_history"][-1], 5)})
        if h == 1:
            for i in d["te"]:
                t = d["ts"][i]
                test_pred_h1.append({"t": t + 1, "actual": round(ipi[t + 1], 3),
                                     "predicted": round(ipi[t] + pred_delta(d["X"][i]), 3), "baseline": round(ipi[t], 3)})
    test_rmse = math.sqrt(se_model_all / cnt_all)
    base_rmse = math.sqrt(se_base_all / cnt_all)
    beats = test_rmse < base_rmse

    # 用全部資料重新訓練並預測
    forecast, interval, warn_extrap = [], [], []
    t_last = n - 1
    final_hist = None
    for h in ds.HORIZONS:
        ts, X, y = ds.build_samples(ipi, exp, util, start_month, feats, h)
        stats = [_mean_std(col) for col in zip(*X)]
        stats = [(m, s if s > 1e-12 else 1.0) for m, s in stats]
        ym, ys = _mean_std(y)
        Xz = [[(v - m) / s for v, (m, s) in zip(x, stats)] for x in X]
        yz = [(v - ym) / ys for v in y]
        r = mlp.train(Xz, yz, hidden_units, epochs, lr, wd, seed + h)
        if r["diverged"]:
            return blocked("全資料重訓發散", "BLOCKED_BY_GUARDRAIL (refit diverged)", "以全部資料重新訓練時發散，請調小學習率")
        if h == 1:
            final_hist = r["loss_history"]
        xl = ds.feature_vector(ipi, exp, util, start_month, feats, t_last, h)
        xz = [(v - m) / s for v, (m, s) in zip(xl, stats)]
        far = [names[i] for i, v in enumerate(xz) if abs(v) > EXTRAP_Z]
        if far:
            warn_extrap.append(f"h={h}：{'、'.join(far)} 超出訓練資料範圍 {EXTRAP_Z:g} 個標準差")
        fc = ipi[t_last] + mlp.predict(r["net"], xz) * ys + ym
        forecast.append(round(fc, 3))
        w = 1.96 * horizons_out[h - 1]["test_rmse"]
        interval.append([round(fc - w, 3), round(fc + w, 3)])

    warnings = list(warn_extrap)
    if not beats:
        warnings.append(f"測試期 RMSE {test_rmse:.3f} 沒有勝過「延續上月」基準 {base_rmse:.3f}，這個模型在這份資料上沒有預測價值，建議直接用基準")
    else:
        worse = [x["h"] for x in horizons_out if not x["beats_baseline"]]
        if worse:
            warnings.append(f"h={worse} 沒有勝過基準，只有部分預測期有改善")
        if horizons_out[-1]["improvement_pct"] is not None and horizons_out[0]["improvement_pct"] is not None \
                and horizons_out[-1]["improvement_pct"] < horizons_out[0]["improvement_pct"] / 2:
            warnings.append("預測期越遠，相對基準的改善越小，第 3 個月的預測不確定性明顯較高")
    ratio = [x["test_rmse"] / x["train_rmse"] for x in horizons_out if x["train_rmse"] > 0]
    if ratio and max(ratio) > OVERFIT_RATIO:
        warnings.append(f"測試 RMSE 是訓練 RMSE 的 {max(ratio):.1f} 倍（> {OVERFIT_RATIO:g}），疑似過擬合；可減少隱藏單元、增加權重衰減或減少 epoch")
    if trained[1]["still_improving"] or trained[2]["still_improving"] or trained[3]["still_improving"]:
        warnings.append("訓練損失在最後 50 個 epoch 仍下降超過 1%，可能尚未收斂；可增加 epoch 或學習率（誤差指標以目前訓練結果為準）")
    if len(h1["te"]) < 20:
        warnings.append(f"測試樣本只有 {len(h1['te'])} 筆，RMSE 差距小於約 10% 不具統計意義")
    warnings.append("誤差只來自單一切分點（最後 20% 時間）的驗證；若未來出現景氣轉折，歷史規律可能失效")
    guardrail = "PASSED_WITH_WARNINGS" if warnings else "PASSED"
    verdict = (f"測試期 RMSE {test_rmse:.3f}，勝過「延續上月」基準 {base_rmse:.3f}（改善 {(1 - test_rmse / base_rmse) * 100:.1f}%）"
               if beats else f"測試期 RMSE {test_rmse:.3f} 未勝過「延續上月」基準 {base_rmse:.3f}")
    log.add(f"測試期（{len(h1['te'])} 個月）逐期 RMSE：" + "；".join(
        f"h={x['h']} 模型 {x['test_rmse']:.3f} vs 基準 {x['baseline_rmse']:.3f}" for x in horizons_out)
        + f"；整體 {verdict}。以全部資料重訓後預測下一季：{forecast}。防呆檢核狀態：{guardrail}。"
        + ("；".join(warnings[:2]) if warnings else ""))

    last_loss = final_hist[-1] if final_hist else None
    answer = f"未來三個月 IPI 預估 {forecast[0]:.1f}、{forecast[1]:.1f}、{forecast[2]:.1f}（現值 {ipi[-1]:.1f}）；{verdict}。{DISCLAIMER}。"
    return finish({
        "status": "success", "found": True,
        "ipi_forecast_next_quarter": forecast, "forecast_interval": interval,
        "training_loss_final": round(hist1[-1], 5),
        "training_loss_final_all": {h: round(trained[h]["loss_history"][-1], 5) for h in ds.HORIZONS},
        "loss_history": [[e, round(v, 6)] for e, v in mlp.downsample(hist1)],
        "loss_history_all": {h: [[e, round(v, 6)] for e, v in mlp.downsample(trained[h]["loss_history"])] for h in ds.HORIZONS},
        "convergence_epoch": trained[1]["convergence_epoch"],
        "test_rmse": round(test_rmse, 4), "baseline_rmse": round(base_rmse, 4), "beats_baseline": beats,
        "improvement_pct": round((1 - test_rmse / base_rmse) * 100, 1) if base_rmse > 0 else None,
        "horizons": horizons_out, "test_predictions_h1": test_pred_h1,
        "split_index": split, "n_months": n, "last_ipi": ipi[-1], "features": feats, "feature_names": names,
        "hyperparameters": {"epochs": epochs, "learning_rate": lr, "hidden_units": hidden_units,
                            "weight_decay": wd, "seed": seed, "n_params_per_net": n_params},
        "data_source": source, "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    r = forecast_ipi_mlp()
    print(json.dumps({k: v for k, v in r.items() if k not in ("steps", "loss_history", "loss_history_all", "test_predictions_h1")},
                     ensure_ascii=False, indent=2))
