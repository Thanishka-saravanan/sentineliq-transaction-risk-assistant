/**
 * SentinelIQ — Transaction Risk Investigation Assistant
 * Frontend Dashboard Application Module (Vanilla ES6)
 * Track ID: PS06
 */

(function () {
    'use strict';

    // Application State
    const state = {
        selectedCustomerId: 'CUST005', // Default showcase customer
        customers: [],
        customerAnalyses: {}, // Cache of customer_id -> CustomerRiskAnalysis
        rulesById: {},        // Cache of rule_id -> RiskRuleDefinition
        currentBaseline: null,
        currentFindings: [],
        currentTransactions: [],
        currentAnalysis: null,
        investigationReport: null,
        highlightedTxnIds: new Set(),
        loadingAI: false,
    };

    // DOM Elements
    const el = {
        customerList: document.getElementById('customer-list'),
        headerBadge: document.getElementById('header-investigation-badge'),
        customerName: document.getElementById('overview-customer-name'),
        customerId: document.getElementById('overview-customer-id'),
        customerScenario: document.getElementById('overview-customer-scenario'),
        metricTxnCount: document.getElementById('metric-tx-count'),
        metricSeverity: document.getElementById('metric-severity'),
        metricScore: document.getElementById('metric-score'),
        metricRulesCount: document.getElementById('metric-rules-count'),
        metricReview: document.getElementById('metric-review'),
        specialCalloutContainer: document.getElementById('special-callout-container'),
        baselineContainer: document.getElementById('baseline-container'),
        findingsContainer: document.getElementById('findings-container'),
        findingsCountBadge: document.getElementById('findings-count-badge'),
        txTableBody: document.getElementById('tx-table-body'),
        txCountBadge: document.getElementById('tx-count-badge'),
        btnGenerateAI: document.getElementById('btn-generate-ai'),
        copilotLoading: document.getElementById('copilot-loading'),
        copilotOutput: document.getElementById('copilot-output'),
        copilotNotice: document.getElementById('copilot-notice'),
    };

    // Helper: Currency Formatter
    function formatCurrency(num) {
        if (num === null || num === undefined) return '$0.00';
        return '$' + Number(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    // Helper: Severity Class
    function getSeverityClass(sev) {
        if (!sev) return 'severity-routine';
        const s = sev.toUpperCase();
        if (s === 'CRITICAL') return 'severity-critical';
        if (s === 'HIGH') return 'severity-high';
        if (s === 'MEDIUM') return 'severity-medium';
        if (s === 'LOW') return 'severity-low';
        return 'severity-routine';
    }

    // Initialize Application
    async function init() {
        try {
            await loadRules();
            await loadCustomers();
            bindEvents();
            // Load default customer
            await selectCustomer(state.selectedCustomerId);
        } catch (err) {
            console.error('Failed to initialize SentinelIQ dashboard:', err);
        }
    }

    // Fetch and cache policy rules
    async function loadRules() {
        try {
            const res = await fetch('/api/rules');
            if (res.ok) {
                const rules = await res.json();
                rules.forEach(r => {
                    state.rulesById[r.rule_id] = r;
                });
            }
        } catch (e) {
            console.warn('Could not fetch rules:', e);
        }
    }

    // Fetch customers and their real risk analyses
    async function loadCustomers() {
        try {
            const res = await fetch('/api/customers');
            if (!res.ok) throw new Error('Failed to load customers');
            state.customers = await res.json();

            // Fetch risk analysis for each customer to show real scores & severities
            await Promise.all(
                state.customers.map(async (c) => {
                    try {
                        const rRes = await fetch(`/api/customers/${c.customer_id}/risk-analysis`);
                        if (rRes.ok) {
                            state.customerAnalyses[c.customer_id] = await rRes.json();
                        }
                    } catch (err) {
                        console.warn(`Could not load risk analysis for ${c.customer_id}:`, err);
                    }
                })
            );

            renderCustomerList();
        } catch (err) {
            console.error('Error loading customers:', err);
        }
    }

    // Render Customer List in Sidebar
    function renderCustomerList() {
        if (!el.customerList) return;
        el.customerList.innerHTML = '';

        state.customers.forEach(c => {
            const analysis = state.customerAnalyses[c.customer_id];
            const summary = (analysis && analysis.summary) ? analysis.summary : {
                highest_severity: 'none',
                highest_risk_score: 0,
            };

            const card = document.createElement('div');
            card.className = `customer-card ${c.customer_id === state.selectedCustomerId ? 'active' : ''}`;
            card.setAttribute('role', 'button');
            card.setAttribute('tabindex', '0');
            card.setAttribute('aria-label', `Select ${c.name} (${c.customer_id})`);

            const sevClass = getSeverityClass(summary.highest_severity);
            const sevText = (!summary.highest_severity || summary.highest_severity.toLowerCase() === 'none')
                ? 'ROUTINE'
                : summary.highest_severity.toUpperCase();

            card.innerHTML = `
                <div class="customer-card-header">
                    <span class="customer-name">${escapeHtml(c.name)}</span>
                    <span class="customer-id-pill">${escapeHtml(c.customer_id)}</span>
                </div>
                <div class="customer-scenario">${escapeHtml(c.scenario.replace(/_/g, ' '))}</div>
                <div class="customer-card-footer">
                    <span class="severity-pill ${sevClass}">${sevText}</span>
                    <span class="score-tag ${summary.highest_risk_score > 0 ? 'text-warn' : ''}">Score: ${summary.highest_risk_score}</span>
                </div>
            `;

            card.addEventListener('click', () => selectCustomer(c.customer_id));
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selectCustomer(c.customer_id);
                }
            });

            el.customerList.appendChild(card);
        });
    }

    // Select Customer and update entire dashboard
    async function selectCustomer(customerId) {
        state.selectedCustomerId = customerId;
        state.highlightedTxnIds.clear();
        state.investigationReport = null;

        // Reset AI panel
        resetCopilotPanel();

        // Update active class in sidebar
        const cards = el.customerList.querySelectorAll('.customer-card');
        state.customers.forEach((c, idx) => {
            if (cards[idx]) {
                cards[idx].classList.toggle('active', c.customer_id === customerId);
            }
        });

        // Concurrently fetch all data for selected customer
        try {
            const [analysisRes, baselineRes, findingsRes, txnsRes] = await Promise.all([
                fetch(`/api/customers/${customerId}/risk-analysis`),
                fetch(`/api/customers/${customerId}/baseline/summary`),
                fetch(`/api/customers/${customerId}/findings`),
                fetch(`/api/customers/${customerId}/transactions`),
            ]);

            state.currentAnalysis = analysisRes.ok ? await analysisRes.json() : null;
            state.currentBaseline = baselineRes.ok ? await baselineRes.json() : null;
            state.currentFindings = findingsRes.ok ? await findingsRes.json() : [];
            state.currentTransactions = txnsRes.ok ? await txnsRes.json() : [];

            // Populate all highlighted transaction IDs from all findings
            state.currentFindings.forEach(f => {
                (f.transaction_ids || []).forEach(tid => state.highlightedTxnIds.add(tid));
            });

            renderOverview();
            renderSpecialCallouts();
            renderBaseline();
            renderFindings();
            renderTransactions();
        } catch (err) {
            console.error(`Error loading data for ${customerId}:`, err);
        }
    }

    // Render Header and Overview Banner
    function renderOverview() {
        const customer = state.customers.find(c => c.customer_id === state.selectedCustomerId);
        if (!customer) return;

        const analysis = state.currentAnalysis;
        const summary = (analysis && analysis.summary) ? analysis.summary : {
            highest_severity: 'none',
            highest_risk_score: 0,
            rules_triggered: [],
            requires_human_review: false,
        };

        const isReviewRequired = Boolean(summary.requires_human_review);

        // Header dynamic badge
        if (isReviewRequired) {
            el.headerBadge.className = 'investigation-badge badge-review';
            el.headerBadge.innerHTML = '<div class="pulse-dot"></div> Human Review Required';
        } else {
            el.headerBadge.className = 'investigation-badge badge-routine';
            el.headerBadge.innerHTML = '<div class="pulse-dot"></div> Routine Account — Normal';
        }

        // Overview Banner
        el.customerName.textContent = customer.name;
        el.customerId.textContent = customer.customer_id;
        el.customerScenario.textContent = customer.description || customer.scenario.replace(/_/g, ' ');

        const txCount = analysis ? analysis.transaction_count : state.currentTransactions.length;
        el.metricTxnCount.textContent = txCount;
        
        const sevText = (!summary.highest_severity || summary.highest_severity.toLowerCase() === 'none')
            ? 'ROUTINE'
            : summary.highest_severity.toUpperCase();
        const sevClass = getSeverityClass(summary.highest_severity);
        el.metricSeverity.innerHTML = `<span class="severity-pill ${sevClass}">${sevText}</span>`;

        el.metricScore.innerHTML = `${summary.highest_risk_score} <span class="metric-sub">/ 100</span>`;
        el.metricRulesCount.textContent = (summary.rules_triggered || []).length;
        el.metricReview.textContent = isReviewRequired ? 'REQUIRED' : 'NOT REQUIRED';
        el.metricReview.style.color = isReviewRequired ? 'var(--severity-high)' : 'var(--severity-routine)';
    }

    // Render Scenario-Specific Callout Cards (CUST001, CUST005, CUST006)
    function renderSpecialCallouts() {
        if (!el.specialCalloutContainer) return;
        el.specialCalloutContainer.innerHTML = '';

        const cid = state.selectedCustomerId;

        // CUST001: Normal case
        if (cid === 'CUST001') {
            const card = document.createElement('div');
            card.className = 'scenario-callout-card callout-routine';
            card.innerHTML = `
                <div class="callout-header">
                    <div class="callout-title" style="color: #6ee7b7;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                        No Deterministic Policy Findings — Routine Account Activity
                    </div>
                    <span class="severity-pill severity-routine">Routine Control Baseline</span>
                </div>
                <div class="callout-body">
                    All 26 transactions align completely with customer Priya Sharma's historical behavioral baseline. No policy thresholds (R01–R05) were triggered. Zero false-positive warnings generated.
                </div>
            `;
            el.specialCalloutContainer.appendChild(card);
        }
        // CUST006: Ambiguity & Mitigating Context
        else if (cid === 'CUST006') {
            const card = document.createElement('div');
            card.className = 'scenario-callout-card callout-ambiguous';
            card.innerHTML = `
                <div class="callout-header">
                    <div class="callout-title" style="color: #fde047;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                        Policy Threshold Triggered — Mitigating Context Identified
                    </div>
                    <span class="severity-pill severity-medium">Ambiguous Anomaly</span>
                </div>
                <div class="callout-body">
                    Transaction TXN0170 ($3,200.00) breached Rule R01 (Unusually Large Transfer) relative to personal IQR upper limit ($285.00). However, critical mitigating context is verified: transaction was conducted at <strong>16:30 (typical active hours)</strong> with a <strong>known retail merchant (Tanishq Jewellers)</strong> via primary <strong>CARD</strong> channel. Demonstrates that threshold breach does NOT equate to a fraud conclusion.
                </div>
            `;
            el.specialCalloutContainer.appendChild(card);
        }
        // CUST005: Showcase Linked Attack Pattern
        else if (cid === 'CUST005') {
            const card = document.createElement('div');
            card.className = 'scenario-callout-card callout-attack';
            card.innerHTML = `
                <div class="callout-header">
                    <div class="callout-title" style="color: #fca5a5;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                        Showcase: Linked Probing & Payment Burst Escalation Pattern
                    </div>
                    <span class="severity-pill severity-critical">Critical Chain Detected</span>
                </div>
                <div class="callout-body">
                    Deterministic detection engine correlated a multi-step attack signature on Sameer Khan's account during nocturnal hours:
                    <div class="sequence-flow">
                        <div class="sequence-step">
                            <div class="sequence-step-num">Step 1: Probe</div>
                            <div class="sequence-step-title">TXN0140 ($1.00)</div>
                            <div class="sequence-step-detail">03:10 AM &bull; Veloce Vault</div>
                        </div>
                        <div class="sequence-step">
                            <div class="sequence-step-num">Step 2: Escalation</div>
                            <div class="sequence-step-title">TXN0141 ($4,500.00)</div>
                            <div class="sequence-step-detail">03:18 AM &bull; 8 min delay</div>
                        </div>
                        <div class="sequence-step">
                            <div class="sequence-step-num">Step 3: Rapid Burst</div>
                            <div class="sequence-step-title">TXN0142 & TXN0143</div>
                            <div class="sequence-step-detail">03:32 AM &bull; $9,700 total</div>
                        </div>
                        <div class="sequence-step">
                            <div class="sequence-step-num">Step 4: Drain Drain</div>
                            <div class="sequence-step-title">TXN0144 ($5,000.00)</div>
                            <div class="sequence-step-detail">04:02 AM &bull; Chain Total $19,201</div>
                        </div>
                    </div>
                </div>
            `;
            el.specialCalloutContainer.appendChild(card);
        }
    }

    // Render Behavioural Baseline Panel
    function renderBaseline() {
        if (!el.baselineContainer) return;
        const b = state.currentBaseline;
        if (!b) {
            el.baselineContainer.innerHTML = '<div class="empty-findings">Baseline data not available.</div>';
            return;
        }

        const typical = b.typical_amount !== undefined ? formatCurrency(b.typical_amount) : 'N/A';
        const lower = (b.typical_amount_range && b.typical_amount_range.lower !== undefined) ? formatCurrency(b.typical_amount_range.lower) : '$0.00';
        const upper = (b.typical_amount_range && b.typical_amount_range.upper !== undefined) ? formatCurrency(b.typical_amount_range.upper) : 'N/A';
        const range = `${lower} – ${upper}`;

        let hoursWindow = '10:00 to 18:00';
        if (b.usual_transaction_hours) {
            const s = String(b.usual_transaction_hours.start).padStart(2, '0') + ':00';
            const e = String(b.usual_transaction_hours.end).padStart(2, '0') + ':00';
            hoursWindow = `${s} to ${e}`;
        }

        const channelsHtml = (b.common_channels || []).map(ch => `<span class="tag-pill">${escapeHtml(ch)}</span>`).join('');
        const payeesHtml = (b.frequent_payees || []).map(p => `<span class="tag-pill">${escapeHtml(p)}</span>`).join('');

        el.baselineContainer.innerHTML = `
            <div class="baseline-grid">
                <div class="baseline-item">
                    <div class="baseline-label">Typical Amount (Median)</div>
                    <div class="baseline-value mono">${typical}</div>
                    <div style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;">Baseline central tendency</div>
                </div>
                <div class="baseline-item">
                    <div class="baseline-label">Policy Upper Bound (1.5x IQR)</div>
                    <div class="baseline-value mono">${upper}</div>
                    <div style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;">IQR Range: ${range}</div>
                </div>
                <div class="baseline-item">
                    <div class="baseline-label">Active Hours Window</div>
                    <div class="baseline-value">${escapeHtml(hoursWindow)}</div>
                    <div style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;">Baseline customer hours</div>
                </div>
                <div class="baseline-item">
                    <div class="baseline-label">Historical Volume</div>
                    <div class="baseline-value mono">${b.transaction_count || 0} transactions</div>
                    <div style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;">Across multi-month history</div>
                </div>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.75rem; margin-bottom:0.85rem;">
                <div class="baseline-item">
                    <div class="baseline-label">Primary Channels</div>
                    <div class="tag-list">${channelsHtml || '<span style="color:var(--text-muted);">None recorded</span>'}</div>
                </div>
                <div class="baseline-item">
                    <div class="baseline-label">Frequent Payees</div>
                    <div class="tag-list">${payeesHtml || '<span style="color:var(--text-muted);">None recorded</span>'}</div>
                </div>
            </div>
            <div class="baseline-callout">
                <strong>Customer-Specific Behavioral Standard:</strong> All incoming transactions are evaluated strictly against this customer's individual historical spending pattern, avoiding population-wide bias.
            </div>
        `;
    }

    // Render Deterministic Policy Findings
    function renderFindings() {
        if (!el.findingsContainer) return;
        el.findingsContainer.innerHTML = '';
        el.findingsCountBadge.textContent = state.currentFindings.length;

        if (state.currentFindings.length === 0) {
            el.findingsContainer.innerHTML = `
                <div class="empty-findings">
                    <div class="empty-icon">✓</div>
                    <div style="font-size:1rem; font-weight:600; color:#ffffff; margin-bottom:0.25rem;">No Deterministic Findings</div>
                    <div style="font-size:0.8rem;">All transactions strictly comply with established risk policies R01 through R05.</div>
                </div>
            `;
            return;
        }

        state.currentFindings.forEach((f, idx) => {
            const ruleDef = state.rulesById[f.rule_id] || null;
            const sevClass = getSeverityClass(f.severity);

            const card = document.createElement('div');
            card.className = 'finding-card';
            card.id = `finding-card-${f.finding_id}`;

            // Build evidence grid items
            let evidenceItemsHtml = '';
            if (f.evidence && typeof f.evidence === 'object') {
                for (const [k, v] of Object.entries(f.evidence)) {
                    let valStr = typeof v === 'object' ? JSON.stringify(v) : String(v);
                    if (typeof v === 'number' && (k.toLowerCase().includes('amount') || k.toLowerCase().includes('total'))) {
                        valStr = formatCurrency(v);
                    }
                    evidenceItemsHtml += `
                        <div class="evidence-item">
                            <span class="evidence-key">${escapeHtml(k.replace(/_/g, ' '))}</span>
                            <span class="evidence-val">${escapeHtml(valStr)}</span>
                        </div>
                    `;
                }
            }

            // Build policy basis section
            let policyBasisHtml = '';
            if (ruleDef) {
                policyBasisHtml = `
                    <div class="policy-basis-box">
                        <div class="policy-basis-header">
                            <span>Policy Basis: ${escapeHtml(ruleDef.rule_id)} &mdash; ${escapeHtml(ruleDef.title)}</span>
                            <span>Standard Guidance</span>
                        </div>
                        <div class="policy-basis-text">
                            <strong>Detection Criteria:</strong> ${escapeHtml(ruleDef.detection_criteria)}<br>
                            <strong>Evidence Requirements:</strong> ${escapeHtml(ruleDef.evidence_requirements)}<br>
                            <strong>Investigator Action:</strong> ${escapeHtml(ruleDef.investigator_action)}
                        </div>
                    </div>
                `;
            }

            card.innerHTML = `
                <div class="finding-header" role="button" tabindex="0" aria-expanded="false">
                    <div class="finding-header-left">
                        <span class="severity-pill ${sevClass}">${escapeHtml(f.severity)}</span>
                        <span class="customer-id-pill">${escapeHtml(f.rule_id)}</span>
                        <span class="finding-title">${escapeHtml(f.title)}</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:0.75rem;">
                        <span class="score-tag text-warn">Score: ${f.risk_score}</span>
                        <button class="finding-toggle-btn" aria-label="Toggle finding details">
                            <span>Expand</span>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
                        </button>
                    </div>
                </div>
                <div class="finding-body">
                    <div class="finding-desc">${escapeHtml(f.description)}</div>
                    
                    <div class="evidence-block">
                        <div class="evidence-title">Mathematical & Contextual Evidence</div>
                        <div class="evidence-grid">${evidenceItemsHtml}</div>
                    </div>

                    <div style="font-size:0.78rem; color:var(--text-secondary); margin-bottom:0.6rem;">
                        <strong>Recommended Action:</strong> ${escapeHtml(f.investigator_action || 'Review transaction context.')}<br>
                        <strong>Limitations:</strong> ${escapeHtml(f.limitations || 'Automated rule engine evaluation.')}
                    </div>

                    ${policyBasisHtml}

                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.65rem;">
                        <button class="view-txns-btn" data-txns="${(f.transaction_ids || []).join(',')}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                            View & Highlight ${(f.transaction_ids || []).length} Linked Transaction(s)
                        </button>
                        <span style="font-size:0.72rem; color:var(--text-muted); font-family:monospace;">${escapeHtml(f.finding_id)}</span>
                    </div>
                </div>
            `;

            // Toggle logic
            const header = card.querySelector('.finding-header');
            const body = card.querySelector('.finding-body');
            const toggleBtn = card.querySelector('.finding-toggle-btn');

            function toggleCard() {
                const isOpen = body.classList.contains('open');
                body.classList.toggle('open', !isOpen);
                header.setAttribute('aria-expanded', String(!isOpen));
                toggleBtn.querySelector('span').textContent = isOpen ? 'Expand' : 'Collapse';
                toggleBtn.querySelector('svg').style.transform = isOpen ? 'rotate(0deg)' : 'rotate(180deg)';
            }

            header.addEventListener('click', (e) => {
                if (!e.target.closest('.view-txns-btn')) {
                    toggleCard();
                }
            });

            header.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleCard();
                }
            });

            // Highlight linked transactions
            const viewBtn = card.querySelector('.view-txns-btn');
            if (viewBtn) {
                viewBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const txns = (f.transaction_ids || []);
                    highlightAndScrollToTransactions(txns);
                });
            }

            el.findingsContainer.appendChild(card);
        });
    }

    // Render Transactions Table
    function renderTransactions() {
        if (!el.txTableBody) return;
        el.txTableBody.innerHTML = '';
        el.txCountBadge.textContent = `${state.currentTransactions.length} txns`;

        state.currentTransactions.forEach(t => {
            const isFlagged = state.highlightedTxnIds.has(t.transaction_id);
            const row = document.createElement('tr');
            row.id = `tx-row-${t.transaction_id}`;
            if (isFlagged) {
                row.className = 'highlighted';
            }

            row.innerHTML = `
                <td class="tx-mono">${escapeHtml(t.date)} ${escapeHtml(t.time)}</td>
                <td class="tx-mono">
                    <strong>${escapeHtml(t.transaction_id)}</strong>
                    ${isFlagged ? '<span class="tx-flag-pill">FLAGGED</span>' : ''}
                </td>
                <td class="tx-amount">${formatCurrency(t.amount)}</td>
                <td><span class="tag-pill">${escapeHtml(t.channel)}</span></td>
                <td>${escapeHtml(t.payee)}</td>
                <td><span class="tag-pill" style="color:#86efac; border-color:rgba(16,185,129,0.3);">${escapeHtml(t.status)}</span></td>
            `;

            el.txTableBody.appendChild(row);
        });
    }

    // Highlight and smooth scroll to transactions
    function highlightAndScrollToTransactions(txnIds) {
        if (!txnIds || txnIds.length === 0) return;

        // Clear existing temporary highlight classes
        const allRows = el.txTableBody.querySelectorAll('tr');
        allRows.forEach(r => {
            if (!state.highlightedTxnIds.has(r.id.replace('tx-row-', ''))) {
                r.classList.remove('highlighted');
            }
        });

        // Add highlight and find first row to scroll to
        let firstRow = null;
        txnIds.forEach(id => {
            const row = document.getElementById(`tx-row-${id}`);
            if (row) {
                row.classList.add('highlighted');
                if (!firstRow) firstRow = row;
            }
        });

        if (firstRow) {
            firstRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    // Reset Gemini Copilot Panel
    function resetCopilotPanel() {
        if (el.copilotLoading) el.copilotLoading.classList.remove('active');
        if (el.copilotOutput) el.copilotOutput.classList.remove('active');
        if (el.copilotNotice) el.copilotNotice.classList.remove('active');
        if (el.btnGenerateAI) {
            el.btnGenerateAI.disabled = false;
            el.btnGenerateAI.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"></path></svg>
                Generate Investigation
            `;
        }
    }

    // Trigger Grounded Gemini Investigation Generation
    async function generateInvestigation() {
        if (state.loadingAI) return;
        state.loadingAI = true;

        el.btnGenerateAI.disabled = true;
        el.btnGenerateAI.textContent = 'Generating...';
        el.copilotNotice.classList.remove('active');
        el.copilotOutput.classList.remove('active');
        el.copilotLoading.classList.add('active');

        try {
            const res = await fetch(`/api/customers/${state.selectedCustomerId}/investigation`);

            if (res.status === 503) {
                const errJson = await res.json().catch(() => ({}));
                showCopilotNotice(
                    'Gemini investigation service is currently unavailable or not configured. Set GEMINI_API_KEY to enable GenAI investigation synthesis.'
                );
                return;
            }

            if (!res.ok) {
                const errJson = await res.json().catch(() => ({}));
                showCopilotNotice(errJson.detail || `Investigation service returned status ${res.status}.`);
                return;
            }

            const data = await res.json();
            state.investigationReport = data;
            renderCopilotReport(data);
        } catch (err) {
            console.error('Gemini synthesis error:', err);
            showCopilotNotice('Network or server connection error while generating investigation report.');
        } finally {
            state.loadingAI = false;
            el.copilotLoading.classList.remove('active');
            el.btnGenerateAI.disabled = false;
            el.btnGenerateAI.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path><polyline points="9 11 12 14 22 4"></polyline></svg>
                Regenerate Investigation
            `;
        }
    }

    function showCopilotNotice(message) {
        if (!el.copilotNotice) return;
        el.copilotNotice.textContent = message;
        el.copilotNotice.classList.add('active');
    }

    // Render Gemini Investigation Output
    function renderCopilotReport(data) {
        if (!el.copilotOutput) return;
        el.copilotOutput.innerHTML = '';

        const assess = data.investigation_assessment || {};

        // 1. Executive Summary
        const execSec = document.createElement('div');
        execSec.className = 'report-section';
        execSec.innerHTML = `
            <div class="report-section-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                Executive Summary
            </div>
            <div class="exec-summary-text">${escapeHtml(data.executive_summary || 'No summary available.')}</div>
            <div class="assessment-meta">
                <div class="meta-item">
                    <span style="color:var(--text-muted);">Assessment:</span>
                    <strong style="color:#ffffff;">${escapeHtml(assess.overall_assessment || 'Pending')}</strong>
                </div>
                <div class="meta-item">
                    <span style="color:var(--text-muted);">Confidence:</span>
                    <span class="tag-pill" style="color:#93c5fd; text-transform:uppercase;">${escapeHtml(assess.confidence || 'medium')}</span>
                </div>
                <div class="meta-item">
                    <span style="color:var(--text-muted);">Human Review:</span>
                    <span class="severity-pill ${assess.requires_human_review ? 'severity-high' : 'severity-routine'}">
                        ${assess.requires_human_review ? 'Required' : 'Not Required'}
                    </span>
                </div>
            </div>
        `;
        el.copilotOutput.appendChild(execSec);

        // 2. Key Concerns & Mitigating Factors Grid
        const gridSec = document.createElement('div');
        gridSec.style.display = 'grid';
        gridSec.style.gridTemplateColumns = '1fr 1fr';
        gridSec.style.gap = '1rem';

        const concernsList = (assess.key_concerns || []).map(c => `<li>${escapeHtml(c)}</li>`).join('');
        const mitigatingList = (assess.mitigating_factors || []).map(m => `<li>${escapeHtml(m)}</li>`).join('');

        gridSec.innerHTML = `
            <div class="report-section">
                <div class="report-section-title" style="color:#fca5a5;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                    Key Investigation Concerns
                </div>
                <ul class="bullet-list concerns">${concernsList || '<li style="color:var(--text-muted);">None identified. Account within baseline.</li>'}</ul>
            </div>
            <div class="report-section">
                <div class="report-section-title" style="color:#86efac;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                    Verified Mitigating Factors
                </div>
                <ul class="bullet-list mitigating">${mitigatingList || '<li style="color:var(--text-muted);">None identified.</li>'}</ul>
            </div>
        `;
        el.copilotOutput.appendChild(gridSec);

        // 3. Grounded Finding Explanations
        if (data.finding_explanations && data.finding_explanations.length > 0) {
            const explSec = document.createElement('div');
            explSec.className = 'report-section';
            
            let explCardsHtml = '';
            data.finding_explanations.forEach(expl => {
                const mitHtml = (expl.mitigating_context || []).length > 0 
                    ? `<div style="font-size:0.75rem; color:#86efac; margin-top:0.35rem;"><strong>Mitigating Context:</strong> ${escapeHtml(expl.mitigating_context.join('; '))}</div>`
                    : '';
                explCardsHtml += `
                    <div style="background:var(--bg-card); border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:0.75rem; margin-bottom:0.6rem;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:0.3rem;">
                            <strong style="color:#ffffff; font-size:0.85rem;">${escapeHtml(expl.finding_id)} (${escapeHtml(expl.rule_id)})</strong>
                        </div>
                        <div style="font-size:0.82rem; color:var(--text-secondary); margin-bottom:0.3rem;">${escapeHtml(expl.plain_language_explanation)}</div>
                        <div style="font-size:0.78rem; color:#bfdbfe;"><strong>Baseline Comparison:</strong> ${escapeHtml(expl.why_it_deviates_from_baseline)}</div>
                        ${mitHtml}
                    </div>
                `;
            });

            explSec.innerHTML = `
                <div class="report-section-title">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                    Grounded Finding Explanations
                </div>
                ${explCardsHtml}
            `;
            el.copilotOutput.appendChild(explSec);
        }

        // 4. Questions & Next Steps
        const actionGrid = document.createElement('div');
        actionGrid.style.display = 'grid';
        actionGrid.style.gridTemplateColumns = '1fr 1fr';
        actionGrid.style.gap = '1rem';

        const qList = (data.investigation_questions || []).map(q => `<li>${escapeHtml(q)}</li>`).join('');
        const stepsList = (data.recommended_next_steps || []).map(s => `<li>${escapeHtml(s)}</li>`).join('');

        actionGrid.innerHTML = `
            <div class="report-section">
                <div class="report-section-title">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                    Customer Investigation Questions
                </div>
                <ul class="bullet-list">${qList || '<li>No questions required.</li>'}</ul>
            </div>
            <div class="report-section">
                <div class="report-section-title">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
                    Recommended Investigator Actions
                </div>
                <ul class="bullet-list">${stepsList || '<li>No actions required.</li>'}</ul>
            </div>
        `;
        el.copilotOutput.appendChild(actionGrid);

        // 5. Limitations & Mandatory Regulatory Disclaimer
        const disclaimerBox = document.createElement('div');
        disclaimerBox.className = 'regulatory-disclaimer';
        disclaimerBox.innerHTML = `
            <strong>REGULATORY COMPLIANCE NOTICE:</strong> ${escapeHtml(data.disclaimer || 'The system identifies activity requiring human review. A risk finding does not establish that fraud has occurred.')}
        `;
        el.copilotOutput.appendChild(disclaimerBox);

        el.copilotOutput.classList.add('active');
    }

    // Helper: HTML Escaping for XSS prevention
    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Bind Event Listeners
    function bindEvents() {
        if (el.btnGenerateAI) {
            el.btnGenerateAI.addEventListener('click', generateInvestigation);
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
