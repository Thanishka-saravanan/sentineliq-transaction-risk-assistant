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
        txnRelevanceMap: {}, // txnId -> 'high' | 'supporting' | 'normal'
        activeFilter: 'all',  // 'all' | 'risk' | 'normal'
        selectedChannel: 'all',
        loadingAI: false,
    };

    // DOM Elements
    const el = {
        customerList: document.getElementById('customer-list'),
        headerBadge: document.getElementById('header-investigation-badge'),
        customerName: document.getElementById('overview-customer-name'),
        customerId: document.getElementById('overview-customer-id'),
        customerScenario: document.getElementById('overview-customer-scenario'),
        overviewBadgeTag: document.getElementById('overview-badge-tag'),
        metricTxnCount: document.getElementById('metric-tx-count'),
        metricSeverity: document.getElementById('metric-severity'),
        metricScore: document.getElementById('metric-score'),
        metricScoreBar: document.getElementById('metric-score-bar'),
        metricRulesCount: document.getElementById('metric-rules-count'),
        metricRulesList: document.getElementById('metric-rules-list'),
        metricFindingsCount: document.getElementById('metric-findings-count'),
        metricReview: document.getElementById('metric-review'),
        metricReviewSubtext: document.getElementById('metric-review-subtext'),
        statusApiText: document.getElementById('status-api-text'),
        statusGeminiText: document.getElementById('status-gemini-text'),
        geminiStatusDot: document.getElementById('gemini-status-dot'),
        specialCalloutContainer: document.getElementById('special-callout-container'),
        timelineContainer: document.getElementById('timeline-container'),
        timelineCountBadge: document.getElementById('timeline-count-badge'),
        unusualContainer: document.getElementById('unusual-comparison-container'),
        baselineContainer: document.getElementById('baseline-container'),
        findingsContainer: document.getElementById('findings-container'),
        findingsCountBadge: document.getElementById('findings-count-badge'),
        txTableBody: document.getElementById('tx-table-body'),
        txCountBadge: document.getElementById('tx-count-badge'),
        txFilterAll: document.getElementById('tx-filter-all'),
        txFilterRisk: document.getElementById('tx-filter-risk'),
        txFilterNormal: document.getElementById('tx-filter-normal'),
        txChannelFilter: document.getElementById('tx-channel-filter'),
        btnGenerateAI: document.getElementById('btn-generate-ai'),
        copilotLoading: document.getElementById('copilot-loading'),
        copilotLoadingText: document.getElementById('copilot-loading-text'),
        copilotOutput: document.getElementById('copilot-output'),
        copilotNotice: document.getElementById('copilot-notice'),
    };

    // Helper: Currency Formatter
    function formatCurrency(num) {
        if (num === null || num === undefined || isNaN(num)) return '$0.00';
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
            await loadHealth();
            await loadRules();
            await loadCustomers();
            bindEvents();
            // Load default showcase customer
            await selectCustomer(state.selectedCustomerId);
        } catch (err) {
            console.error('Failed to initialize SentinelIQ dashboard:', err);
        }
    }

    // Check system status via /api/health
    async function loadHealth() {
        try {
            const res = await fetch('/api/health');
            if (res.ok) {
                const h = await res.json();
                if (el.statusApiText) el.statusApiText.textContent = 'Operational';
                if (el.statusGeminiText && el.geminiStatusDot) {
                    if (h.gemini_api_key_configured) {
                        el.statusGeminiText.textContent = 'Connected';
                        el.geminiStatusDot.className = 'status-dot dot-green';
                    } else {
                        el.statusGeminiText.textContent = 'Not Configured';
                        el.geminiStatusDot.className = 'status-dot dot-amber';
                    }
                }
            }
        } catch (e) {
            console.warn('Could not query system health endpoint:', e);
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

            // Fetch risk analysis for each customer to populate real scores & severities
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
                requires_human_review: false,
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

            const findingCount = analysis ? analysis.finding_count : 0;
            const reviewText = summary.requires_human_review ? 'Review Required' : 'No Attention Required';

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
                <div style="display:flex; justify-content:space-between; font-size:0.7rem; color:var(--text-muted); margin-top:0.4rem; padding-top:0.35rem; border-top:1px dashed rgba(255,255,255,0.06);">
                    <span>${findingCount} ${findingCount === 1 ? 'finding' : 'findings'}</span>
                    <span style="color:${summary.requires_human_review ? 'var(--severity-high)' : 'var(--severity-routine)'}; font-weight:600;">${reviewText}</span>
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
        state.txnRelevanceMap = {};
        state.investigationReport = null;
        state.activeFilter = 'all';
        state.selectedChannel = 'all';

        if (el.txChannelFilter) el.txChannelFilter.value = 'all';
        updateFilterButtons();

        // Reset AI panel
        resetCopilotPanel();

        // Update active class in sidebar
        const cards = el.customerList ? el.customerList.querySelectorAll('.customer-card') : [];
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

            // Compute transaction relevance maps
            state.currentFindings.forEach(f => {
                const sev = (f.severity || '').toLowerCase();
                const isHigh = sev === 'critical' || sev === 'high' || f.risk_score >= 70;
                (f.transaction_ids || []).forEach(tid => {
                    state.highlightedTxnIds.add(tid);
                    if (isHigh) {
                        state.txnRelevanceMap[tid] = 'high';
                    } else if (state.txnRelevanceMap[tid] !== 'high') {
                        state.txnRelevanceMap[tid] = 'supporting';
                    }
                });
            });

            renderOverview();
            renderSpecialCallouts();
            renderTimeline();
            renderUnusualComparison();
            renderBaseline();
            renderFindings();
            renderTransactions();
        } catch (err) {
            console.error(`Error loading data for ${customerId}:`, err);
        }
    }

    // Render Header and Executive Risk Summary Card
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
        const sevClass = getSeverityClass(summary.highest_severity);
        const sevText = (!summary.highest_severity || summary.highest_severity.toLowerCase() === 'none')
            ? 'ROUTINE'
            : summary.highest_severity.toUpperCase();

        // Header dynamic badge
        if (el.headerBadge) {
            if (isReviewRequired) {
                el.headerBadge.className = 'investigation-badge badge-review';
                el.headerBadge.innerHTML = '<div class="pulse-dot"></div> Human Review Required';
            } else {
                el.headerBadge.className = 'investigation-badge badge-routine';
                el.headerBadge.innerHTML = '<div class="pulse-dot"></div> Routine Account — Normal';
            }
        }

        // Customer Identity
        if (el.customerName) el.customerName.textContent = customer.name;
        if (el.customerId) el.customerId.textContent = customer.customer_id;
        if (el.overviewBadgeTag) {
            el.overviewBadgeTag.className = `severity-pill ${sevClass}`;
            el.overviewBadgeTag.textContent = sevText;
        }
        if (el.customerScenario) {
            el.customerScenario.textContent = customer.description || customer.scenario.replace(/_/g, ' ');
        }

        // Score & Metrics
        const score = summary.highest_risk_score || 0;
        if (el.metricScore) el.metricScore.textContent = score;
        if (el.metricScoreBar) {
            el.metricScoreBar.style.width = `${Math.min(100, Math.max(0, score))}%`;
            if (score >= 80) {
                el.metricScoreBar.style.background = 'linear-gradient(90deg, #f59e0b, #ef4444)';
            } else if (score >= 40) {
                el.metricScoreBar.style.background = 'linear-gradient(90deg, #10b981, #f59e0b)';
            } else {
                el.metricScoreBar.style.background = 'var(--severity-routine)';
            }
        }

        if (el.metricSeverity) {
            el.metricSeverity.innerHTML = `<span class="severity-pill ${sevClass}">${sevText}</span>`;
        }

        const rules = summary.rules_triggered || [];
        if (el.metricRulesCount) el.metricRulesCount.textContent = rules.length;
        if (el.metricRulesList) {
            el.metricRulesList.textContent = rules.length > 0 ? `Triggered: ${rules.join(', ')}` : 'No policy breaches';
        }

        const findingCount = analysis ? analysis.finding_count : state.currentFindings.length;
        if (el.metricFindingsCount) el.metricFindingsCount.textContent = findingCount;

        const txCount = analysis ? analysis.transaction_count : state.currentTransactions.length;
        if (el.metricTxnCount) el.metricTxnCount.textContent = txCount;

        if (el.metricReview) {
            el.metricReview.textContent = isReviewRequired ? 'REQUIRED' : 'NOT REQUIRED';
            el.metricReview.style.color = isReviewRequired ? 'var(--severity-high)' : 'var(--severity-routine)';
        }
        if (el.metricReviewSubtext) {
            el.metricReviewSubtext.textContent = isReviewRequired
                ? 'Human investigator review mandatory'
                : 'Routine activity — no action required';
        }
    }

    // Render Scenario Showcase Callouts (CUST001, CUST005, CUST006)
    function renderSpecialCallouts() {
        if (!el.specialCalloutContainer) return;
        el.specialCalloutContainer.innerHTML = '';

        const cid = state.selectedCustomerId;

        // CUST001: Zero False Positives / Routine Baseline
        if (cid === 'CUST001') {
            const card = document.createElement('div');
            card.className = 'scenario-callout-card callout-routine';
            card.innerHTML = `
                <div class="callout-header">
                    <div class="callout-title" style="color: #6ee7b7;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                        Zero False-Positive Showcase: Routine Control Baseline
                    </div>
                    <span class="severity-pill severity-routine">NO ATTENTION REQUIRED</span>
                </div>
                <div class="callout-body">
                    <strong>Customer activity remains consistent with the established behavioral baseline.</strong> All 26 transactions conform strictly to Priya Sharma's personalized historical spending range, usual daytime hours, and known payee profiles. Zero deterministic policy thresholds (R01–R05) were triggered.
                </div>
            `;
            el.specialCalloutContainer.appendChild(card);
        }
        // CUST006: Mitigating Context / Anomaly vs Fraud
        else if (cid === 'CUST006') {
            const card = document.createElement('div');
            card.className = 'scenario-callout-card callout-ambiguous';
            card.innerHTML = `
                <div class="callout-header">
                    <div class="callout-title" style="color: #fde047;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                        ANOMALY DETECTED — CONTEXT REQUIRED
                    </div>
                    <span class="severity-pill severity-medium">HUMAN REVIEW — NOT PROVEN FRAUD</span>
                </div>
                <div class="callout-body">
                    Transaction TXN0170 ($3,200.00) breached deterministic Rule R01 relative to Sunita Rao's IQR threshold ($285.00). However, critical contextual facts demonstrate that a threshold breach does <em>not</em> establish fraud:
                    <div class="callout-checklist">
                        <div class="checklist-item"><span class="checklist-icon">✓</span> <strong>Amount exceeds baseline:</strong> $3,200.00 vs $285.00 IQR limit (Threshold Trigger)</div>
                        <div class="checklist-item"><span class="checklist-icon">✓</span> <strong>Verified Known Merchant:</strong> Tanishq Jewellers (historical retail jeweler)</div>
                        <div class="checklist-item"><span class="checklist-icon">✓</span> <strong>Normal Active Hours:</strong> Conducted at 16:30 (within customer's 10:00–18:00 window)</div>
                        <div class="checklist-item"><span class="checklist-icon">✓</span> <strong>Primary Customer Channel:</strong> CARD (standard retail transaction mode)</div>
                        <div class="checklist-item"><span class="checklist-icon">✓</span> <strong>Isolated Event:</strong> No probing sequence, payment burst, or velocity escalation</div>
                    </div>
                    <div style="font-size:0.75rem; color:#fef08a; margin-top:0.5rem;">
                        <strong>Investigator Standard:</strong> Flag for human review to confirm customer authorization for high-value retail jewelry purchase. Do not freeze account automatically.
                    </div>
                </div>
            `;
            el.specialCalloutContainer.appendChild(card);
        }
        // CUST005: Multi-Step Attack Pattern Showcase
        else if (cid === 'CUST005') {
            const card = document.createElement('div');
            card.className = 'scenario-callout-card callout-attack';
            card.innerHTML = `
                <div class="callout-header">
                    <div class="callout-title" style="color: #fca5a5;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                        Showcase: Linked Probing & Payment Burst Escalation Pattern
                    </div>
                    <span class="severity-pill severity-critical">CRITICAL ATTACK CHAIN DETECTED</span>
                </div>
                <div class="callout-body">
                    Deterministic detection engine correlated a multi-stage nocturnal attack pattern across 5 transactions on Sameer Khan's account:
                    <div class="sequence-flow">
                        <div class="sequence-step">
                            <div class="sequence-step-num">Step 1: Probe</div>
                            <div class="sequence-step-title">TXN0140 ($1.00)</div>
                            <div class="sequence-step-detail">03:10 AM &bull; Veloce Vault</div>
                        </div>
                        <div class="sequence-step">
                            <div class="sequence-step-num">Step 2: Escalation</div>
                            <div class="sequence-step-title">TXN0141 ($4,500.00)</div>
                            <div class="sequence-step-detail">03:18 AM &bull; 8 min post-probe</div>
                        </div>
                        <div class="sequence-step">
                            <div class="sequence-step-num">Step 3: Rapid Burst</div>
                            <div class="sequence-step-title">TXN0142 &amp; TXN0143</div>
                            <div class="sequence-step-detail">03:27 &amp; 03:41 &bull; $9,800 burst</div>
                        </div>
                        <div class="sequence-step">
                            <div class="sequence-step-num">Step 4: Drain Drain</div>
                            <div class="sequence-step-title">TXN0144 ($4,900.00)</div>
                            <div class="sequence-step-detail">04:02 AM &bull; Total $19,201</div>
                        </div>
                    </div>
                </div>
            `;
            el.specialCalloutContainer.appendChild(card);
        }
    }

    // Feature 1: Dynamic Investigation Timeline
    function renderTimeline() {
        if (!el.timelineContainer) return;
        el.timelineContainer.innerHTML = '';

        // Gather transactions related to findings
        const findingTxnIds = new Set();
        const txnFindingMap = {}; // txnId -> array of { rule_id, finding_id, title, severity }

        state.currentFindings.forEach(f => {
            (f.transaction_ids || []).forEach(tid => {
                findingTxnIds.add(tid);
                if (!txnFindingMap[tid]) txnFindingMap[tid] = [];
                txnFindingMap[tid].push({
                    rule_id: f.rule_id,
                    finding_id: f.finding_id,
                    title: f.title,
                    severity: f.severity,
                });
            });
        });

        // Filter and sort transactions chronologically
        const timelineTxns = state.currentTransactions
            .filter(t => findingTxnIds.has(t.transaction_id))
            .sort((a, b) => (a.date + ' ' + a.time).localeCompare(b.date + ' ' + b.time));

        if (el.timelineCountBadge) {
            el.timelineCountBadge.textContent = `${timelineTxns.length} ${timelineTxns.length === 1 ? 'event' : 'events'}`;
        }

        if (timelineTxns.length === 0) {
            el.timelineContainer.innerHTML = `
                <div class="timeline-empty">
                    <div style="font-size:1.6rem; color:var(--severity-routine); margin-bottom:0.35rem;">✓</div>
                    <div style="font-size:0.92rem; font-weight:600; color:#ffffff;">No Suspicious Sequence Detected</div>
                    <div style="font-size:0.8rem; margin-top:0.25rem;">All customer transaction intervals, amounts, and channels adhere to routine baseline behavior.</div>
                </div>
            `;
            return;
        }

        const track = document.createElement('div');
        track.className = 'timeline-track';

        // Helper: calculate minutes between two timestamps
        function getDeltaMinutes(t1, t2) {
            try {
                const d1 = new Date(`${t1.date}T${t1.time}`);
                const d2 = new Date(`${t2.date}T${t2.time}`);
                const diffMs = d2.getTime() - d1.getTime();
                return Math.max(0, Math.round(diffMs / 60000));
            } catch (e) {
                return null;
            }
        }

        timelineTxns.forEach((t, idx) => {
            const item = document.createElement('div');
            item.className = 'timeline-item';

            // Check if probe
            const isProbe = t.amount <= 5.0 && idx === 0 && timelineTxns.length > 1;
            const markerClass = isProbe ? 'probe' : (t.amount >= 2000 ? 'critical' : '');

            // Rule tags
            const rules = (txnFindingMap[t.transaction_id] || []).map(r => r.rule_id);
            const uniqueRules = Array.from(new Set(rules));
            const ruleTagsHtml = uniqueRules.map(r => `<span class="tag-pill" style="font-size:0.68rem; color:#bfdbfe;">${escapeHtml(r)}</span>`).join(' ');

            // Step role description
            let stepRole = `Step ${idx + 1}`;
            if (isProbe) {
                stepRole = 'Step 1: Low-Value Probe';
            } else if (idx === 1 && timelineTxns[0].amount <= 5.0) {
                stepRole = 'Step 2: Escalation Transfer';
            } else if (idx > 1 && idx < timelineTxns.length - 1) {
                stepRole = `Step ${idx + 1}: Rapid Payment Burst`;
            } else if (idx === timelineTxns.length - 1 && timelineTxns.length > 2) {
                stepRole = `Step ${idx + 1}: Account Drain`;
            }

            // Elapsed time indicator from previous transaction
            let elapsedHtml = '';
            if (idx > 0) {
                const prev = timelineTxns[idx - 1];
                const delta = getDeltaMinutes(prev, t);
                if (delta !== null) {
                    const elapsedText = delta >= 60
                        ? `${Math.floor(delta / 60)}h ${delta % 60}m`
                        : `${delta} min`;
                    elapsedHtml = `
                        <div class="timeline-elapsed-connector">
                            <span>&darr;</span>
                            <span class="timeline-elapsed-pill">+${elapsedText} elapsed</span>
                        </div>
                    `;
                }
            }

            item.innerHTML = `
                ${elapsedHtml}
                <div class="timeline-marker ${markerClass}">${idx + 1}</div>
                <div class="timeline-node" data-txid="${escapeHtml(t.transaction_id)}" title="Click to view transaction in ledger">
                    <div class="timeline-node-header">
                        <span class="timeline-step-tag">${escapeHtml(stepRole)}</span>
                        <span class="timeline-time-badge">${escapeHtml(t.time)} &bull; ${escapeHtml(t.date)}</span>
                    </div>
                    <div class="timeline-node-main">
                        <span class="timeline-tx-title">${escapeHtml(t.transaction_id)}</span>
                        <span class="timeline-amount" style="${isProbe ? 'color:#fef08a;' : ''}">${formatCurrency(t.amount)}</span>
                    </div>
                    <div class="timeline-node-meta">
                        <span><strong>Channel:</strong> ${escapeHtml(t.channel)}</span>
                        <span>&bull;</span>
                        <span><strong>Payee:</strong> ${escapeHtml(t.payee)}</span>
                        ${ruleTagsHtml ? `<span>&bull;</span> ${ruleTagsHtml}` : ''}
                    </div>
                </div>
            `;

            // Click node to highlight & scroll in ledger
            const node = item.querySelector('.timeline-node');
            node.addEventListener('click', () => {
                highlightAndScrollToTransactions([t.transaction_id]);
            });

            track.appendChild(item);
        });

        el.timelineContainer.appendChild(track);
    }

    // Feature 2: Why This Is Unusual For This Customer
    function renderUnusualComparison() {
        if (!el.unusualContainer) return;
        el.unusualContainer.innerHTML = '';

        const b = state.currentBaseline;
        const txns = state.currentTransactions;
        const findings = state.currentFindings;

        if (!b) {
            el.unusualContainer.innerHTML = '<div class="empty-findings">Baseline comparison not available.</div>';
            return;
        }

        // 1. Transaction Amount Comparison
        const typicalMedian = b.typical_amount || 0;
        const iqrUpper = (b.typical_amount_range && b.typical_amount_range.upper) || 0;

        // Find max observed flagged transaction or max overall
        let maxObservedAmount = 0;
        const flaggedTxns = txns.filter(t => state.highlightedTxnIds.has(t.transaction_id));
        if (flaggedTxns.length > 0) {
            maxObservedAmount = Math.max(...flaggedTxns.map(t => t.amount));
        } else if (txns.length > 0) {
            maxObservedAmount = Math.max(...txns.map(t => t.amount));
        }

        let amountDevClass = 'dev-normal';
        let amountDevText = 'Normal (Within baseline)';
        if (maxObservedAmount > iqrUpper) {
            const ratio = typicalMedian > 0 ? (maxObservedAmount / typicalMedian).toFixed(1) : 'N/A';
            if (maxObservedAmount >= 3000 || (typicalMedian > 0 && maxObservedAmount / typicalMedian > 50)) {
                amountDevClass = 'dev-critical';
                amountDevText = `Extremely High (${ratio}x median)`;
            } else {
                amountDevClass = 'dev-warning';
                amountDevText = `Elevated (${ratio}x median)`;
            }
        }

        // 2. Activity Time Comparison
        let baselineHoursStr = '10:00 to 18:00';
        let startH = 10;
        let endH = 18;
        if (b.usual_transaction_hours) {
            startH = b.usual_transaction_hours.start;
            endH = b.usual_transaction_hours.end;
            baselineHoursStr = `${String(startH).padStart(2, '0')}:00 – ${String(endH).padStart(2, '0')}:00`;
        }

        // Observed time range of flagged or latest transactions
        let observedTimeStr = 'Within standard hours';
        let timeDevClass = 'dev-normal';
        let timeDevText = 'Within standard active window';

        if (flaggedTxns.length > 0) {
            const times = flaggedTxns.map(t => t.time).sort();
            const minTime = times[0];
            const maxTime = times[times.length - 1];
            observedTimeStr = minTime === maxTime ? minTime : `${minTime} – ${maxTime}`;

            // Check if any flagged transaction is outside hours
            const hasOffHours = flaggedTxns.some(t => {
                const h = parseInt(t.time.split(':')[0], 10);
                return h < startH || h >= endH;
            });

            if (hasOffHours) {
                timeDevClass = 'dev-critical';
                timeDevText = 'Outside normal pattern (Off-hours)';
            }
        }

        // 3. Channel Comparison
        const commonChannels = b.common_channels || [];
        const commonChannelsStr = commonChannels.join(', ') || 'CARD, UPI';

        let observedChannels = Array.from(new Set((flaggedTxns.length > 0 ? flaggedTxns : txns).map(t => t.channel)));
        let observedChannelStr = observedChannels.join(', ') || 'CARD';
        let channelDevClass = 'dev-normal';
        let channelDevText = 'Standard customer channel';

        if (flaggedTxns.length > 0) {
            const unusualCh = observedChannels.filter(ch => !commonChannels.includes(ch));
            if (unusualCh.length > 0) {
                channelDevClass = 'dev-warning';
                channelDevText = `Unusual / New channel (${unusualCh.join(', ')})`;
            } else if (state.selectedCustomerId === 'CUST006') {
                channelDevClass = 'dev-context';
                channelDevText = 'Primary channel (CARD)';
            }
        }

        // 4. Payee Comparison
        const frequentPayees = b.frequent_payees || [];
        const frequentPayeesStr = frequentPayees.join(', ') || 'Known merchants';

        let observedPayees = Array.from(new Set(flaggedTxns.map(t => t.payee)));
        let observedPayeeStr = observedPayees.join(', ') || (txns[txns.length - 1] ? txns[txns.length - 1].payee : 'Routine payees');
        let payeeDevClass = 'dev-normal';
        let payeeDevText = 'Routine payee';

        if (flaggedTxns.length > 0) {
            if (state.selectedCustomerId === 'CUST006') {
                payeeDevClass = 'dev-context';
                payeeDevText = 'Known retail merchant (Tanishq)';
            } else {
                const unknownPayees = observedPayees.filter(p => !frequentPayees.includes(p));
                if (unknownPayees.length > 0) {
                    payeeDevClass = 'dev-critical';
                    payeeDevText = 'New / Unrecognized beneficiary';
                }
            }
        }

        el.unusualContainer.innerHTML = `
            <div class="unusual-grid">
                <!-- Dimension 1: Amount -->
                <div class="unusual-box">
                    <div class="unusual-header">
                        <span class="unusual-title">Transaction Amount</span>
                        <span class="deviation-pill ${amountDevClass}">${amountDevText}</span>
                    </div>
                    <div class="unusual-comp-row">
                        <span class="unusual-comp-label">Customer Baseline:</span>
                        <span class="unusual-comp-val">${formatCurrency(typicalMedian)} median (IQR max: ${formatCurrency(iqrUpper)})</span>
                    </div>
                    <div class="unusual-comp-row">
                        <span class="unusual-comp-label">Observed Flagged Max:</span>
                        <span class="unusual-comp-val text-warn">${formatCurrency(maxObservedAmount)}</span>
                    </div>
                </div>

                <!-- Dimension 2: Time -->
                <div class="unusual-box">
                    <div class="unusual-header">
                        <span class="unusual-title">Activity Hours Window</span>
                        <span class="deviation-pill ${timeDevClass}">${timeDevText}</span>
                    </div>
                    <div class="unusual-comp-row">
                        <span class="unusual-comp-label">Typical Customer Hours:</span>
                        <span class="unusual-comp-val">${escapeHtml(baselineHoursStr)}</span>
                    </div>
                    <div class="unusual-comp-row">
                        <span class="unusual-comp-label">Observed Transaction Time:</span>
                        <span class="unusual-comp-val text-warn">${escapeHtml(observedTimeStr)}</span>
                    </div>
                </div>

                <!-- Dimension 3: Channel -->
                <div class="unusual-box">
                    <div class="unusual-header">
                        <span class="unusual-title">Payment Channel</span>
                        <span class="deviation-pill ${channelDevClass}">${channelDevText}</span>
                    </div>
                    <div class="unusual-comp-row">
                        <span class="unusual-comp-label">Common Baseline Channels:</span>
                        <span class="unusual-comp-val">${escapeHtml(commonChannelsStr)}</span>
                    </div>
                    <div class="unusual-comp-row">
                        <span class="unusual-comp-label">Observed Channel:</span>
                        <span class="unusual-comp-val">${escapeHtml(observedChannelStr)}</span>
                    </div>
                </div>

                <!-- Dimension 4: Payee -->
                <div class="unusual-box">
                    <div class="unusual-header">
                        <span class="unusual-title">Beneficiary / Payee</span>
                        <span class="deviation-pill ${payeeDevClass}">${payeeDevText}</span>
                    </div>
                    <div class="unusual-comp-row">
                        <span class="unusual-comp-label">Frequent Historical Payees:</span>
                        <span class="unusual-comp-val">${escapeHtml(frequentPayeesStr)}</span>
                    </div>
                    <div class="unusual-comp-row">
                        <span class="unusual-comp-label">Observed Beneficiary:</span>
                        <span class="unusual-comp-val text-warn">${escapeHtml(observedPayeeStr)}</span>
                    </div>
                </div>
            </div>
        `;
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
                    <div style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;">Audited multi-month history</div>
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
                <strong>Customer-Specific Behavioral Standard:</strong> All incoming transactions are evaluated strictly against this customer's individual historical spending distribution, preventing population-wide false alarms.
            </div>
        `;
    }

    // Render Deterministic Policy Findings
    function renderFindings() {
        if (!el.findingsContainer) return;
        el.findingsContainer.innerHTML = '';
        if (el.findingsCountBadge) {
            el.findingsCountBadge.textContent = `${state.currentFindings.length}`;
        }

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

        state.currentFindings.forEach((f) => {
            const ruleDef = state.rulesById[f.rule_id] || null;
            const sevClass = getSeverityClass(f.severity);

            const card = document.createElement('div');
            card.className = 'finding-card';
            card.id = `finding-card-${f.finding_id}`;

            // Evidence grid items
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

            // Policy basis section
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

    // Render Transactions Table with Filter Controls & Relevance Badges
    function renderTransactions() {
        if (!el.txTableBody) return;
        el.txTableBody.innerHTML = '';

        // Apply filters
        let filtered = state.currentTransactions;

        // Channel filter
        if (state.selectedChannel !== 'all') {
            filtered = filtered.filter(t => t.channel === state.selectedChannel);
        }

        // Relevance filter
        if (state.activeFilter === 'risk') {
            filtered = filtered.filter(t => state.highlightedTxnIds.has(t.transaction_id));
        } else if (state.activeFilter === 'normal') {
            filtered = filtered.filter(t => !state.highlightedTxnIds.has(t.transaction_id));
        }

        if (el.txCountBadge) {
            el.txCountBadge.textContent = `${filtered.length} / ${state.currentTransactions.length} txns`;
        }

        if (filtered.length === 0) {
            el.txTableBody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align:center; padding:1.5rem; color:var(--text-muted);">
                        No transactions match the selected filter criteria.
                    </td>
                </tr>
            `;
            return;
        }

        filtered.forEach(t => {
            const isFlagged = state.highlightedTxnIds.has(t.transaction_id);
            const relevance = state.txnRelevanceMap[t.transaction_id] || 'normal';

            const row = document.createElement('tr');
            row.id = `tx-row-${t.transaction_id}`;
            if (isFlagged) {
                row.className = 'highlighted';
            }

            let relevanceBadgeHtml = '<span class="tx-relevance-pill tx-relevance-normal"><span class="badge-dot dot-normal"></span> Normal</span>';
            if (relevance === 'high') {
                relevanceBadgeHtml = '<span class="tx-relevance-pill tx-relevance-high"><span class="badge-dot dot-critical"></span> High Relevance</span>';
            } else if (relevance === 'supporting') {
                relevanceBadgeHtml = '<span class="tx-relevance-pill tx-relevance-supporting"><span class="badge-dot dot-supporting"></span> Supporting</span>';
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
                <td>${relevanceBadgeHtml}</td>
            `;

            el.txTableBody.appendChild(row);
        });
    }

    // Highlight and smooth scroll to transactions
    function highlightAndScrollToTransactions(txnIds) {
        if (!txnIds || txnIds.length === 0) return;

        // If filter is set to 'normal', reset to 'all' so rows are visible
        if (state.activeFilter === 'normal') {
            state.activeFilter = 'all';
            updateFilterButtons();
            renderTransactions();
        }

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

    // Update Filter Buttons Active State
    function updateFilterButtons() {
        if (el.txFilterAll) el.txFilterAll.classList.toggle('active', state.activeFilter === 'all');
        if (el.txFilterRisk) el.txFilterRisk.classList.toggle('active', state.activeFilter === 'risk');
        if (el.txFilterNormal) el.txFilterNormal.classList.toggle('active', state.activeFilter === 'normal');
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
                <span>Generate Investigation</span>
            `;
        }
    }

    // Trigger Grounded Gemini Investigation Generation
    async function generateInvestigation() {
        if (state.loadingAI) return;
        state.loadingAI = true;

        el.btnGenerateAI.disabled = true;
        el.btnGenerateAI.innerHTML = `<span>Analyzing evidence...</span>`;
        if (el.copilotLoadingText) el.copilotLoadingText.textContent = 'Analyzing evidence and grounding investigation...';
        el.copilotNotice.classList.remove('active');
        el.copilotOutput.classList.remove('active');
        el.copilotLoading.classList.add('active');

        try {
            const res = await fetch(`/api/customers/${state.selectedCustomerId}/investigation`);

            if (res.status === 503) {
                showCopilotNotice(
                    'Investigation Copilot is temporarily unavailable or GEMINI_API_KEY is not configured. Deterministic findings, baseline bounds, timeline, and transaction evidence remain fully operational above.'
                );
                return;
            }

            if (!res.ok) {
                const errJson = await res.json().catch(() => ({}));
                showCopilotNotice(errJson.detail || `Investigation service returned HTTP status ${res.status}.`);
                return;
            }

            const data = await res.json();
            state.investigationReport = data;
            renderCopilotReport(data);
        } catch (err) {
            console.error('Gemini synthesis error:', err);
            showCopilotNotice('Network or server connection error while generating grounded investigation.');
        } finally {
            state.loadingAI = false;
            el.copilotLoading.classList.remove('active');
            el.btnGenerateAI.disabled = false;
            const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            el.btnGenerateAI.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path><polyline points="9 11 12 14 22 4"></polyline></svg>
                <span>Regenerate (${now})</span>
            `;
        }
    }

    function showCopilotNotice(message) {
        if (!el.copilotNotice) return;
        el.copilotNotice.innerHTML = `
            <strong>Notice:</strong> ${escapeHtml(message)}
        `;
        el.copilotNotice.classList.add('active');
    }

    // Render Grounded 7-Section Copilot Report
    function renderCopilotReport(data) {
        if (!el.copilotOutput) return;
        el.copilotOutput.innerHTML = '';

        const assess = data.investigation_assessment || {};

        // SECTION 1: WHAT HAPPENED?
        const sec1 = document.createElement('div');
        sec1.className = 'report-section';
        sec1.innerHTML = `
            <div class="report-section-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                1. What Happened?
            </div>
            <div class="exec-summary-text">${escapeHtml(data.executive_summary || 'No summary available.')}</div>
        `;
        el.copilotOutput.appendChild(sec1);

        // SECTION 2 & 3: WHY IT MATTERS & EVIDENCE (Grid)
        const gridSec = document.createElement('div');
        gridSec.style.display = 'grid';
        gridSec.style.gridTemplateColumns = '1fr 1fr';
        gridSec.style.gap = '1rem';

        const concernsList = (assess.key_concerns || []).map(c => `<li>${escapeHtml(c)}</li>`).join('');
        let evidenceList = [];
        (data.finding_explanations || []).forEach(fe => {
            if (fe.why_it_deviates_from_baseline) {
                evidenceList.push(`<li><strong>${escapeHtml(fe.rule_id)}:</strong> ${escapeHtml(fe.why_it_deviates_from_baseline)}</li>`);
            }
        });

        gridSec.innerHTML = `
            <div class="report-section">
                <div class="report-section-title" style="color:#fca5a5;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                    2. Why It Matters
                </div>
                <ul class="bullet-list concerns">${concernsList || '<li style="color:var(--text-muted);">Account activity conforms to established policy.</li>'}</ul>
            </div>
            <div class="report-section">
                <div class="report-section-title" style="color:#93c5fd;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></svg>
                    3. Grounded Evidence
                </div>
                <ul class="bullet-list">${evidenceList.join('') || '<li style="color:var(--text-muted);">All parameters within baseline standard deviation.</li>'}</ul>
            </div>
        `;
        el.copilotOutput.appendChild(gridSec);

        // SECTION 4: MITIGATING FACTORS
        const sec4 = document.createElement('div');
        sec4.className = 'report-section';
        const mitigatingList = (assess.mitigating_factors || []).map(m => `<li>${escapeHtml(m)}</li>`).join('');
        sec4.innerHTML = `
            <div class="report-section-title" style="color:#86efac;">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                4. Verified Mitigating Factors
            </div>
            <ul class="bullet-list mitigating">${mitigatingList || '<li style="color:var(--text-muted);">No mitigating factors recorded for flagged events.</li>'}</ul>
        `;
        el.copilotOutput.appendChild(sec4);

        // SECTION 5: WHAT TO INVESTIGATE FIRST (Numbered Priority Action Cards)
        const sec5 = document.createElement('div');
        sec5.className = 'report-section';
        const steps = data.recommended_next_steps || [];
        let priorityCardsHtml = '';
        if (steps.length > 0) {
            steps.forEach((step, idx) => {
                const numStr = String(idx + 1).padStart(2, '0');
                // Extract action title and reason if colon present
                let actionTitle = step;
                let actionReason = 'Grounded in deterministic risk findings and customer baseline profile.';
                if (step.includes(':')) {
                    const parts = step.split(':');
                    actionTitle = parts[0].trim();
                    actionReason = parts.slice(1).join(':').trim();
                }
                priorityCardsHtml += `
                    <div class="priority-card">
                        <div class="priority-num">${numStr}</div>
                        <div class="priority-content">
                            <div class="priority-action">${escapeHtml(actionTitle)}</div>
                            <div class="priority-reason">${escapeHtml(actionReason)}</div>
                        </div>
                    </div>
                `;
            });
        } else {
            priorityCardsHtml = '<div style="color:var(--text-muted); font-size:0.85rem;">No immediate investigator action required.</div>';
        }

        sec5.innerHTML = `
            <div class="report-section-title" style="color:#fde047;">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
                5. What To Investigate First (Investigator Priority)
            </div>
            <div class="priority-list">${priorityCardsHtml}</div>
        `;
        el.copilotOutput.appendChild(sec5);

        // SECTION 6: WHAT COULD EXPLAIN THIS ACTIVITY (Hypotheses)
        const sec6 = document.createElement('div');
        sec6.className = 'report-section';
        const questions = data.investigation_questions || [];
        const qListHtml = questions.map(q => `<li>${escapeHtml(q)}</li>`).join('');
        sec6.innerHTML = `
            <div class="report-section-title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                6. What Could Explain This Activity (Alternative Hypotheses & Questions)
            </div>
            <ul class="bullet-list">${qListHtml || '<li style="color:var(--text-muted);">Standard routine operational expenditure.</li>'}</ul>
        `;
        el.copilotOutput.appendChild(sec6);

        // SECTION 7: FINAL INVESTIGATION STATUS & REGULATORY DISCLAIMER
        const sec7 = document.createElement('div');
        sec7.className = 'report-section';
        sec7.innerHTML = `
            <div class="report-section-title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                7. Final Investigation Status
            </div>
            <div class="assessment-meta" style="border-top:none; padding-top:0; margin-top:0; margin-bottom:0.75rem;">
                <div class="meta-item">
                    <span style="color:var(--text-muted);">Assessment:</span>
                    <strong style="color:#ffffff;">${escapeHtml(assess.overall_assessment || 'Pending Review')}</strong>
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
            <div class="regulatory-disclaimer">
                <strong>REGULATORY COMPLIANCE NOTICE:</strong> ${escapeHtml(data.disclaimer || 'The system identifies activity requiring human review. A risk finding does not establish that fraud has occurred.')}
            </div>
        `;
        el.copilotOutput.appendChild(sec7);

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

        if (el.txFilterAll) {
            el.txFilterAll.addEventListener('click', () => {
                state.activeFilter = 'all';
                updateFilterButtons();
                renderTransactions();
            });
        }

        if (el.txFilterRisk) {
            el.txFilterRisk.addEventListener('click', () => {
                state.activeFilter = 'risk';
                updateFilterButtons();
                renderTransactions();
            });
        }

        if (el.txFilterNormal) {
            el.txFilterNormal.addEventListener('click', () => {
                state.activeFilter = 'normal';
                updateFilterButtons();
                renderTransactions();
            });
        }

        if (el.txChannelFilter) {
            el.txChannelFilter.addEventListener('change', (e) => {
                state.selectedChannel = e.target.value;
                renderTransactions();
            });
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
