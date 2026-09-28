document.addEventListener("DOMContentLoaded", () => {
    // Tab switching
    const navTabs = document.querySelectorAll(".nav-tab");
    const tabContents = document.querySelectorAll(".tab-content");

    navTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            navTabs.forEach(t => t.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            tab.classList.add("active");
            const target = tab.dataset.tab;
            document.getElementById(`tab-${target}`).classList.add("active");

            if (target === "indexing") loadIndexVisuals();
            if (target === "storage") loadStorageVisuals();
        });
    });

    // Subtabs for Workbench Results
    const subtabBtns = document.querySelectorAll(".subtab-btn");
    subtabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            subtabBtns.forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".subtab-content").forEach(c => c.classList.remove("active"));
            btn.classList.add("active");
            document.getElementById(btn.dataset.subtab + "-view").classList.add("active");
        });
    });

    // SQL Editor & Execution
    const sqlEditor = document.getElementById("sql-editor");
    const btnRunQuery = document.getElementById("btn-run-query");
    const btnClearQuery = document.getElementById("btn-clear-query");
    const resultTable = document.getElementById("query-result-table");
    const planContainer = document.getElementById("query-plan-tree-container");
    const statsBar = document.getElementById("stats-bar");
    const statTime = document.getElementById("stat-time");
    const statRows = document.getElementById("stat-rows");
    const statPlan = document.getElementById("stat-plan");

    // Fetch System Catalog Tables
    loadSystemCatalog();

    document.getElementById("btn-refresh-tables").addEventListener("click", loadSystemCatalog);

    // Preset Queries
    document.querySelectorAll(".preset-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            sqlEditor.value = btn.dataset.sql;
            runQuery();
        });
    });

    btnClearQuery.addEventListener("click", () => {
        sqlEditor.value = "";
    });

    btnRunQuery.addEventListener("click", runQuery);

    sqlEditor.addEventListener("keydown", (e) => {
        if (e.ctrlKey && e.key === "Enter") {
            e.preventDefault();
            runQuery();
        }
    });

    function runQuery() {
        const sql = sqlEditor.value.trim();
        if (!sql) return;

        resultTable.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-circle-notch fa-spin"></i> Executing query...</div>`;

        fetch("/api/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sql: sql })
        })
        .then(res => res.json())
        .then(data => {
            statsBar.classList.remove("hidden");
            statTime.textContent = `${data.execution_time_ms} ms`;
            statRows.textContent = data.row_count;
            statPlan.textContent = data.plan_tree ? data.plan_tree.name : "N/A";

            if (data.error) {
                resultTable.innerHTML = `<div class="empty-state" style="color: var(--accent-red);"><i class="fa-solid fa-triangle-exclamation"></i><p>${data.error}</p></div>`;
                planContainer.innerHTML = `<div class="empty-state"><p>Query Error</p></div>`;
                return;
            }

            if (data.message && data.rows.length === 0) {
                resultTable.innerHTML = `<div class="empty-state"><i class="fa-solid fa-circle-check" style="color: var(--accent-green);"></i><p>${data.message}</p></div>`;
                loadSystemCatalog();
            } else if (data.columns && data.columns.length > 0) {
                renderResultTable(data.columns, data.rows);
            }

            if (data.plan_tree) {
                renderPlanTree(data.plan_tree);
            }
        })
        .catch(err => {
            resultTable.innerHTML = `<div class="empty-state" style="color: var(--accent-red);"><p>API Connection Error: ${err}</p></div>`;
        });
    }

    function renderResultTable(columns, rows) {
        if (rows.length === 0) {
            resultTable.innerHTML = `<div class="empty-state"><i class="fa-solid fa-inbox"></i><p>0 rows returned.</p></div>`;
            return;
        }

        let html = `<table class="data-table"><thead><tr>`;
        columns.forEach(col => { html += `<th>${col}</th>`; });
        html += `</tr></thead><tbody>`;

        rows.forEach(row => {
            html += `<tr>`;
            columns.forEach(col => {
                const val = row[col] !== undefined ? row[col] : "";
                html += `<td>${val}</td>`;
            });
            html += `</tr>`;
        });

        html += `</tbody></table>`;
        resultTable.innerHTML = html;
    }

    function renderPlanTree(node) {
        function buildNodeHTML(n) {
            let html = `<div class="tree-node-card">
                <div class="node-header">${n.name}</div>`;
            if (n.table) html += `<div style="font-size:0.8rem; color: var(--accent-cyan);">Table: ${n.table}</div>`;
            if (n.column) html += `<div style="font-size:0.8rem; color: var(--accent-purple);">Column: ${n.column}</div>`;
            if (n.cost) html += `<div style="font-size:0.75rem; color: var(--accent-gold);">${n.cost}</div>`;
            if (n.children && n.children.length > 0) {
                html += `<div style="margin-top: 0.5rem; padding-left: 1rem; border-left: 2px solid var(--border-color);">`;
                n.children.forEach(c => { html += buildNodeHTML(c); });
                html += `</div>`;
            }
            html += `</div>`;
            return html;
        }
        planContainer.innerHTML = buildNodeHTML(node);
    }

    function loadSystemCatalog() {
        fetch("/api/tables")
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById("schema-tree-container");
                if (!data.tables || data.tables.length === 0) {
                    container.innerHTML = `<div class="empty-state"><p>No tables found.</p></div>`;
                    return;
                }

                let html = "";
                data.tables.forEach(t => {
                    html += `<div class="table-node">
                        <div class="table-node-header">
                            <span><i class="fa-solid fa-table"></i> ${t.name}</span>
                            <span style="font-size: 0.75rem; color: var(--text-muted);">${t.num_pages} page(s)</span>
                        </div>
                        <div class="col-list">`;
                    t.columns.forEach(c => {
                        html += `<div class="col-item">
                            <span>${c.name} ${c.primary_key ? '<i class="fa-solid fa-key" style="color: var(--accent-gold);"></i>' : ''}</span>
                            <span class="col-type">${c.col_type}</span>
                        </div>`;
                    });
                    html += `</div></div>`;
                });
                container.innerHTML = html;
            });
    }

    // Index Visualizer Loading
    const btnRenderIndex = document.getElementById("btn-render-index");
    btnRenderIndex.addEventListener("click", loadIndexVisuals);

    function loadIndexVisuals() {
        const table = document.getElementById("select-table-index").value;
        const btreeContainer = document.getElementById("btree-graph-container");
        const hashContainer = document.getElementById("hash-graph-container");

        btreeContainer.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading B+ Tree...</div>`;
        hashContainer.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading Hash Index...</div>`;

        // Fetch B+ Tree
        fetch(`/api/visual/btree?table=${table}&column=id`)
            .then(res => res.json())
            .then(data => {
                if (data.tree) {
                    renderBTreeGraph(data.tree, btreeContainer);
                } else {
                    btreeContainer.innerHTML = `<div class="empty-state"><p>No B+ Tree index found for ${table}(id)</p></div>`;
                }
            });

        // Fetch Hash Index
        fetch(`/api/visual/hash?table=${table}&column=category`)
            .then(res => res.json())
            .then(data => {
                if (data.hash) {
                    renderHashGraph(data.hash, hashContainer);
                } else {
                    hashContainer.innerHTML = `<div class="empty-state"><p>No Hash Index found for ${table}(category)</p></div>`;
                }
            });
    }

    function renderBTreeGraph(node, container) {
        function renderNode(n) {
            let html = `<div class="tree-node-card">
                <div class="node-header">${n.type} Node (${n.id})</div>
                <div class="node-keys">`;
            n.keys.forEach(k => {
                html += `<span class="key-badge">${k}</span>`;
            });
            html += `</div>`;

            if (n.type === "LEAF") {
                html += `<div style="font-size:0.75rem; color: var(--accent-green); margin-top:0.4rem;">Record IDs: ${n.rid_count}</div>`;
            }

            if (n.children && n.children.length > 0) {
                html += `<div style="display: flex; gap: 0.5rem; margin-top: 0.75rem; padding-top: 0.5rem; border-top: 1px dashed var(--border-color);">`;
                n.children.forEach(c => { html += renderNode(c); });
                html += `</div>`;
            }
            html += `</div>`;
            return html;
        }
        container.innerHTML = renderNode(node);
    }

    function renderHashGraph(hashData, container) {
        let html = `<div style="margin-bottom: 0.75rem; font-size: 0.85rem; color: var(--text-muted);">
            Global Depth: <strong style="color: var(--accent-gold);">${hashData.global_depth}</strong> | Directory Size: <strong>${hashData.directory_size}</strong>
        </div>`;

        html += `<div class="hash-bucket-grid">`;
        hashData.buckets.forEach(b => {
            html += `<div class="bucket-card">
                <div class="bucket-title">${b.bucket_id} (Local Depth: ${b.local_depth})</div>
                <div style="font-size:0.78rem; color: var(--text-muted); margin-bottom: 0.4rem;">Entries (${b.count}/${b.capacity}):</div>`;
            b.entries.forEach(e => {
                html += `<div style="font-size: 0.75rem; font-family: var(--font-code); background: var(--bg-primary); padding: 0.2rem 0.4rem; border-radius: 4px; margin-bottom: 0.2rem;">
                    key: <span style="color: var(--accent-cyan);">${e.key}</span> -> RID (${e.rid[0]}, ${e.rid[1]})
                </div>`;
            });
            html += `</div>`;
        });
        html += `</div>`;
        container.innerHTML = html;
    }

    // Storage & Buffer Pool Visuals
    function loadStorageVisuals() {
        fetch(`/api/visual/bufferpool?table=products`)
            .then(res => res.json())
            .then(data => {
                if (data.buffer_pool) {
                    const bp = data.buffer_pool;
                    document.getElementById("bp-hit-ratio").textContent = `${bp.hit_ratio_percent}%`;
                    document.getElementById("bp-hits").textContent = bp.hits;
                    document.getElementById("bp-misses").textContent = bp.misses;

                    const grid = document.getElementById("buffer-pool-grid");
                    let html = "";
                    bp.frames.forEach(f => {
                        html += `<div class="bp-frame ${f.is_dirty ? 'dirty' : ''}">
                            <div class="frame-id">Frame Page #${f.page_id}</div>
                            <div style="font-size: 0.75rem; color: var(--text-muted);">Pins: ${f.pin_count} | Slots: ${f.num_slots}</div>
                            <div style="font-size: 0.75rem; color: ${f.is_dirty ? 'var(--accent-gold)' : 'var(--accent-green)'};">
                                ${f.is_dirty ? '<i class="fa-solid fa-pen-to-square"></i> Dirty (Needs Writeback)' : '<i class="fa-solid fa-check"></i> Clean'}
                            </div>
                        </div>`;
                    });
                    grid.innerHTML = html;
                }
            });

        // Load Page 0
        fetch(`/api/visual/page?table=products&page_id=0`)
            .then(res => res.json())
            .then(data => {
                if (data.page) {
                    const p = data.page;
                    const container = document.getElementById("page-layout-visualizer");
                    let html = `<div style="margin-bottom: 0.75rem; font-size: 0.85rem;">
                        Page ID: <strong>#${p.page_id}</strong> | Type: <strong>${p.page_type}</strong> | Slots: <strong>${p.num_slots}</strong> | Free Space: <strong>${p.free_space_bytes} B</strong>
                    </div>`;

                    html += `<div class="page-memory-bar">
                        <div class="mem-segment mem-header">Header (9B)</div>
                        <div class="mem-segment mem-slots">Slot Array (${p.num_slots * 4}B)</div>
                        <div class="mem-segment mem-free">Free Space (${p.free_space_bytes}B)</div>
                        <div class="mem-segment mem-tuples">Tuples Payload</div>
                    </div>`;

                    html += `<div style="margin-top: 1rem;">
                        <h4 style="font-size: 0.85rem; font-family: var(--font-heading); margin-bottom: 0.5rem;">Slot Array Offsets:</h4>
                        <table class="data-table" style="font-size: 0.8rem;">
                            <thead><tr><th>Slot ID</th><th>Offset</th><th>Length</th><th>Status</th></tr></thead>
                            <tbody>`;
                    p.slots.forEach(s => {
                        html += `<tr>
                            <td>#${s.slot_id}</td>
                            <td>${s.offset}</td>
                            <td>${s.length} B</td>
                            <td>${s.is_deleted ? '<span style="color:var(--accent-red)">Deleted</span>' : '<span style="color:var(--accent-green)">Active</span>'}</td>
                        </tr>`;
                    });
                    html += `</tbody></table></div>`;
                    container.innerHTML = html;
                }
            });
    }

    // Benchmark Runner
    document.getElementById("btn-run-benchmark").addEventListener("click", () => {
        const container = document.getElementById("benchmark-results-container");
        container.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-bolt fa-spin"></i> Executing 500 queries benchmark...</div>`;

        fetch("/api/benchmark", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ records: 500 })
        })
        .then(res => res.json())
        .then(bm => {
            let html = `<div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1rem;">
                Target Search Key: <strong style="color: var(--accent-cyan);">${bm.target_key}</strong> across <strong>${bm.record_count}</strong> records.
            </div>`;

            const maxTime = Math.max(bm.seq_scan_ms, bm.btree_scan_ms, bm.hash_scan_ms, 0.001);

            html += `
                <div class="bm-bar-card">
                    <div class="bm-bar-header">
                        <span><i class="fa-solid fa-align-justify" style="color: var(--accent-red);"></i> Full Sequential Table Scan (O(N))</span>
                        <span>${bm.seq_scan_ms} ms</span>
                    </div>
                    <div class="bm-progress-bg">
                        <div class="bm-progress-fill fill-seq" style="width: 100%;">Baseline</div>
                    </div>
                </div>

                <div class="bm-bar-card" style="margin-top: 1rem;">
                    <div class="bm-bar-header">
                        <span><i class="fa-solid fa-sitemap" style="color: var(--accent-blue);"></i> B+ Tree Index Scan (O(log N))</span>
                        <span>${bm.btree_scan_ms} ms (<strong style="color: var(--accent-cyan);">${bm.speedup_btree}x faster</strong>)</span>
                    </div>
                    <div class="bm-progress-bg">
                        <div class="bm-progress-fill fill-btree" style="width: ${Math.max((bm.btree_scan_ms / maxTime) * 100, 5)}%;">${bm.speedup_btree}x Faster</div>
                    </div>
                </div>

                <div class="bm-bar-card" style="margin-top: 1rem;">
                    <div class="bm-bar-header">
                        <span><i class="fa-solid fa-hashtag" style="color: var(--accent-green);"></i> Extendible Hash Index Scan (O(1))</span>
                        <span>${bm.hash_scan_ms} ms (<strong style="color: var(--accent-green);">${bm.speedup_hash}x faster</strong>)</span>
                    </div>
                    <div class="bm-progress-bg">
                        <div class="bm-progress-fill fill-hash" style="width: ${Math.max((bm.hash_scan_ms / maxTime) * 100, 5)}%;">${bm.speedup_hash}x Faster</div>
                    </div>
                </div>
            `;

            container.innerHTML = html;
        });
    });
});
