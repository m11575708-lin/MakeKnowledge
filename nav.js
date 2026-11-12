/**
 * nav.js - 13 頁共用左側導覽選單
 *
 * 用法：各頁面放一個空的容器，並在 body 結尾載入本檔：
 *   <aside id="navMount" class="lg:col-span-1 bg-white rounded-xl border border-slate-200 p-4 shadow-xs space-y-4 h-fit"></aside>
 *   <script src="nav.js"></script>
 *
 * 新增頁面完成後，只需把下方對應項目的 ready 改成 true（只改這一個檔案）。
 */
(function () {
    const PAGES = [
        { no: "01", title: "製造知識庫檢索與智慧問答", href: "page01_knowledge_chat.html",   skill: "Skill 01",    ready: true  },
        { no: "02", title: "製造規範與技術文件收錄",   href: "page02_doc_collection.html",   skill: "Skill 26",    ready: true  },
        { no: "03", title: "工廠圖資與維修履歷匯入",   href: "page03_import_cleaning.html",  skill: "Skill 27",    ready: true  },
        { no: "04", title: "知識庫維運與回答品質評估", href: "page04_ops_eval.html",         skill: "Skill 28–29", ready: true  },
        { no: "05", title: "公開法規與商品檢驗查詢",   href: "page05_regulations_search.html", skill: "Skill 01·02", ready: true  },
        { no: "06", title: "設備壽命預測",             href: "page06_rul_prediction.html",   skill: "Skill 03–05", ready: true  },
        { no: "07", title: "設備突發故障風險評估",     href: "page07_failure_risk.html",     skill: "Skill 06–08", ready: true  },
        { no: "08", title: "歷史維修案例與備品推薦",   href: "page08_case_retrieval.html",   skill: "Skill 09–11", ready: true  },
        { no: "09", title: "維修案例登錄與故障碼驗證", href: "page09_repair_log.html",       skill: "Skill 12–13", ready: true },
        { no: "10", title: "品質異常根本原因分析",     href: "page10_root_cause.html",       skill: "Skill 14–16", ready: true  },
        { no: "11", title: "鋼板表面缺陷分類",         href: "page11_steel_defects.html",    skill: "Skill 17–19", ready: true  },
        { no: "12", title: "製程參數分群與 SPC 監控",  href: "page12_spc_clustering.html",   skill: "Skill 20–22", ready: true },
        { no: "13", title: "智慧生產指數預測",         href: "page13_index_forecast.html",   skill: "Skill 23–25", ready: true },
    ];

    const current = (location.pathname.split("/").pop() || "page01_knowledge_chat.html").toLowerCase();

    function item(p) {
        const isCurrent = p.href.toLowerCase() === current;
        const badge = (cls) => `<span class="text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap ${cls}">${p.skill}</span>`;
        const label = `<span class="leading-snug">${p.no}. ${p.title}</span>`;

        if (isCurrent) {
            return `<a href="${p.href}" aria-current="page" class="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-sky-50 text-sky-700 font-bold border border-sky-200">${label}${badge("bg-sky-200 text-sky-800")}</a>`;
        }
        if (p.ready) {
            return `<a href="${p.href}" class="flex items-center justify-between gap-2 p-2.5 rounded-lg text-slate-600 hover:bg-slate-50 transition-colors">${label}${badge("bg-slate-100 text-slate-500")}</a>`;
        }
        return `<div class="flex items-center justify-between gap-2 p-2.5 rounded-lg text-slate-400 cursor-not-allowed" title="此頁尚在建置中">${label}<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-400 whitespace-nowrap">建置中</span></div>`;
    }

    function render() {
        const mount = document.getElementById("navMount");
        if (!mount) return;
        const readyCount = PAGES.filter((p) => p.ready).length;
        mount.innerHTML = `
            <div class="font-bold text-sm text-slate-900 border-b border-slate-100 pb-2 flex items-center justify-between">
                <span>📋 系統選單功能網頁</span>
                <span class="text-xs font-normal text-slate-400">已上線 ${readyCount} / ${PAGES.length} 頁</span>
            </div>
            <nav class="space-y-1 text-xs font-medium">${PAGES.map(item).join("")}</nav>`;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", render);
    } else {
        render();
    }
})();
