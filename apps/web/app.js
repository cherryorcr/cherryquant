const params = new URLSearchParams(window.location.search);
const apiBase = (params.get('api') || 'http://127.0.0.1:8000').replace(/\/$/, '');
const state = { dataset: null, bars: [], draft: null, selectedCandidate: null, run: null };

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
}

function showError(message) { const error = $('#error'); error.hidden = false; error.textContent = message; }
function clearError() { $('#error').hidden = true; $('#error').textContent = ''; }

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body);
    throw new Error(`${response.status}: ${detail}`);
  }
  return body;
}

function conditionLabel(condition) {
  if (!condition) return '—';
  if (condition.type === 'all_of') return (condition.conditions || []).map(conditionLabel).join(' 且 ');
  const labels = { close_above_sma: '收盘价高于', close_below_sma: '收盘价低于', close_crosses_above_sma: '收盘价上穿', close_crosses_below_sma: '收盘价下穿' };
  return `${labels[condition.type] || condition.type} SMA(${condition.period ?? '?'})`;
}

function supportLabel(support) { return support === 'supported' ? '可运行' : support === 'partial' ? '部分支持' : '暂不支持'; }
function supportClass(support) { return support === 'supported' ? 'supported' : support === 'partial' ? 'partial' : 'unsupported'; }
function metric(label, value, accent = '') { return `<div class="metric ${accent}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`; }

function updatePromptCount() { $('#prompt-count').textContent = `${$('#strategy-prompt').value.length} / 4000`; }

function renderDataset() {
  const data = state.dataset;
  $('#connection').textContent = 'API 已连接';
  $('#connection').classList.add('ok');
  $('#api-endpoint').textContent = apiBase.replace(/^https?:\/\//, '');
  $('#run-context').textContent = `${data.symbol} · ${data.frequency} · ${data.note}`;
  $('#research-range').textContent = `${data.research_start}—${data.research_end}`;
  $('#holdout-range').textContent = `${data.holdout_start}—${data.holdout_end}`;
}

function renderClarifications(items = []) {
  const box = $('#clarifications');
  if (!items.length) { box.hidden = true; box.replaceChildren(); return; }
  box.hidden = false;
  box.innerHTML = `<strong>生成时需要留意</strong><ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
}

function candidateMarkup(candidate, selected = false) {
  const ir = candidate.ir || {};
  const sizing = ir.sizing || {};
  const conditions = `<div class="condition-pair"><span>入场</span><strong>${escapeHtml(conditionLabel(ir.entry))}</strong><span>退出</span><strong>${escapeHtml(conditionLabel(ir.exit))}</strong></div>`;
  const list = (items, fallback) => items?.length ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : `<p class="muted">${fallback}</p>`;
  const factors = (ir.factors || []).map((factor) => {
    const params = Object.entries(factor.params || {}).map(([key, value]) => `${key}=${value}`).join(', ');
    return `${factor.metric}${params ? ` (${params})` : ''} · ${factor.explanation}`;
  });
  return `<article class="candidate-card ${selected ? 'selected' : ''} ${supportClass(candidate.support)}" data-candidate-id="${escapeHtml(candidate.id)}">
    <div class="candidate-top"><div><span class="candidate-number">${escapeHtml(candidate.id)}</span><h3>${escapeHtml(candidate.title)}</h3></div><span class="support-badge ${supportClass(candidate.support)}">${supportLabel(candidate.support)}</span></div>
    <p class="candidate-summary">${escapeHtml(candidate.summary)}</p>${conditions}
    <div class="candidate-meta"><span>仓位 ${escapeHtml(sizing.position_fraction ?? '—')}</span><span>手数 ${escapeHtml(sizing.lot_size ?? '—')}</span><span>${escapeHtml(candidate.form)}</span></div>
    <details><summary>因子、数据与风险</summary><div class="details-grid"><div><small>因子</small>${list(factors, '未补充')}</div><div><small>数据要求</small>${list(candidate.data_requirements, '未补充')}</div><div><small>假设</small>${list(candidate.assumptions, '未补充')}</div><div><small>风险提示</small>${list(candidate.risk_notes, '未补充')}</div></div></details>
    <button type="button" class="select-button">${selected ? '已选择 · 查看下方确认区' : '选择这个候选'}</button>
  </article>`;
}

function renderCandidates(envelope) {
  state.draft = envelope;
  $('#draft-meta').textContent = `${envelope.candidates.length} 个候选 · ${envelope.metadata?.provider || 'provider'}`;
  renderClarifications(envelope.clarifications);
  const list = $('#candidate-list');
  list.className = 'candidate-list';
  list.innerHTML = envelope.candidates.map((candidate) => candidateMarkup(candidate, candidate.id === state.selectedCandidate?.id)).join('');
  $$('.candidate-card').forEach((card) => card.addEventListener('click', (event) => {
    if (event.target.closest('details')) return;
    const candidate = envelope.candidates.find((item) => item.id === card.dataset.candidateId);
    if (candidate) selectCandidate(candidate);
  }));
}

function selectCandidate(candidate) {
  state.selectedCandidate = candidate;
  renderCandidates(state.draft);
  const panel = $('#confirm-panel');
  panel.hidden = false;
  const ir = candidate.ir || {};
  const executable = candidate.support === 'supported' && candidate.form === 'condition_set';
  $('#selected-summary').innerHTML = `<div class="selected-kicker">已选择候选</div><h3>${escapeHtml(candidate.title)}</h3><p>${escapeHtml(candidate.summary)}</p><div class="selected-rule"><span>入场</span><strong>${escapeHtml(conditionLabel(ir.entry))}</strong><span>退出</span><strong>${escapeHtml(conditionLabel(ir.exit))}</strong></div>${executable ? '' : '<div class="inline-warning">这个候选包含当前引擎尚未执行的能力，不能直接运行。</div>'}`;
  $('#run-button').disabled = !executable || !$('#confirm-checkbox').checked;
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderSummary(summary) {
  $('#summary').innerHTML = [
    metric('状态', summary.status, summary.status === 'COMPLETED' ? 'positive' : ''),
    metric('交易数', summary.trade_count),
    metric('期末权益', summary.final_equity),
    metric('总收益', summary.total_return, Number(summary.total_return) >= 0 ? 'positive' : 'negative'),
    metric('已实现盈亏', summary.realized_pnl, Number(summary.realized_pnl) >= 0 ? 'positive' : 'negative'),
    metric('未成交订单', summary.not_filled_order_count),
  ].join('');
}

function statusClass(status) { return status === 'PASS' ? 'status-pass' : status === 'FAIL' ? 'status-fail' : 'status-unavailable'; }
function traceReason(trace) {
  const entry = trace.condition_results.entry; const exit = trace.condition_results.exit;
  const parts = [`入场：${entry.reason}`, `退出：${exit.reason}`];
  if (trace.order_attempt) { const order = trace.order_attempt; parts.push(order.status === 'FILLED' ? `${order.side === 'buy' ? '买入' : '卖出'}成交 ${order.price}` : `未成交：${order.reason}`); }
  if (trace.warnings?.length) parts.push(trace.warnings.join('、'));
  return parts.join('；');
}

function renderTraces(traces) {
  const table = $('#trace-table'); table.replaceChildren();
  for (const trace of traces) {
    const row = document.createElement('tr');
    const entry = trace.condition_results.entry; const exit = trace.condition_results.exit; const order = trace.order_attempt;
    row.innerHTML = `<td><code>${escapeHtml(trace.date)}</code></td><td class="${statusClass(entry.status)}">${escapeHtml(entry.status)}</td><td class="${statusClass(exit.status)}">${escapeHtml(exit.status)}</td><td><span class="signal ${trace.signal || ''}">${escapeHtml(trace.signal || '—')}</span></td><td>${order ? `${escapeHtml(order.status)}${order.price ? ` @ ${escapeHtml(order.price)}` : ''}` : '—'}</td><td>${escapeHtml(traceReason(trace))}</td>`;
    row.addEventListener('click', () => { $$('#trace-table tr').forEach((item) => item.classList.remove('active')); row.classList.add('active'); });
    table.appendChild(row);
  }
}

function svgElement(name, attrs = {}) { const node = document.createElementNS('http://www.w3.org/2000/svg', name); Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value))); return node; }

function renderChart(bars, traces) {
  const svg = $('#chart'); svg.replaceChildren(); if (!bars.length) return;
  const width = 900; const height = 300; const pad = { left: 48, right: 18, top: 24, bottom: 38 };
  const closes = bars.map((bar) => Number(bar.close)); const min = Math.min(...closes); const max = Math.max(...closes); const range = max - min || 1;
  const x = (index) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, bars.length - 1)); const y = (value) => pad.top + (max - value) * ((height - pad.top - pad.bottom) / range);
  for (let i = 0; i < 4; i += 1) { const value = min + range * (i / 3); svg.appendChild(svgElement('line', { x1: pad.left, x2: width - pad.right, y1: y(value), y2: y(value), class: 'chart-grid' })); const label = svgElement('text', { x: 8, y: y(value) + 4, class: 'chart-label' }); label.textContent = value.toFixed(2); svg.appendChild(label); }
  svg.appendChild(svgElement('polyline', { points: closes.map((value, index) => `${x(index)},${y(value)}`).join(' '), class: 'chart-line' }));
  bars.forEach((bar, index) => { const label = svgElement('text', { x: x(index), y: height - 13, class: 'chart-label', 'text-anchor': 'middle' }); label.textContent = bar.date.slice(4); svg.appendChild(label); });
  const byDate = new Map(traces.map((trace) => [trace.date, trace]));
  bars.forEach((bar, index) => { const trace = byDate.get(bar.date); if (!trace) return; const markers = []; if (trace.signal === 'entry') markers.push(['mark-entry', -12]); if (trace.signal === 'exit') markers.push(['mark-exit', 12]); if (trace.order_attempt?.status === 'FILLED') markers.push(['mark-fill', 0]); markers.forEach(([className, offset]) => svg.appendChild(svgElement('circle', { cx: x(index), cy: y(Number(bar.close)) + offset, r: 6, class: className }))); });
}

async function generateDraft() {
  clearError(); const prompt = $('#strategy-prompt').value.trim(); if (prompt.length < 8) { showError('请先用至少 8 个字描述想验证的交易想法。'); return; }
  const button = $('#generate-button'); button.disabled = true; button.classList.add('loading'); button.innerHTML = '<span class="spinner"></span>生成中…';
  try { const body = await request('/v1/strategy-drafts', { method: 'POST', body: JSON.stringify({ prompt, symbol: $('#symbol').value.trim() || '600000.SH', dataset_id: 'demo-synthetic', candidate_count: Number($('#candidate-count').value) }) }); state.selectedCandidate = null; $('#confirm-panel').hidden = true; renderCandidates(body.draft); } catch (error) { showError(error.message); } finally { button.disabled = false; button.classList.remove('loading'); button.innerHTML = '<span class="button-icon">✦</span>生成候选规则'; }
}

async function confirmRun() {
  clearError(); if (!state.draft || !state.selectedCandidate) return;
  const button = $('#run-button'); button.disabled = true; button.innerHTML = '<span class="spinner"></span>运行中…';
  const config = { initial_cash: $('#initial-cash').value, commission_rate: $('#commission-rate').value, min_commission: $('#min-commission').value, stamp_duty_rate: $('#stamp-duty-rate').value, engine_version: 'm1.0' };
  try { const body = await request(`/v1/strategy-drafts/${encodeURIComponent(state.draft.request_id)}/confirm`, { method: 'POST', body: JSON.stringify({ candidate_id: state.selectedCandidate.id, config }) }); state.run = body.result; $('#results-section').hidden = false; $('#run-id').textContent = `RUN ${body.run_id.slice(0, 10)}`; renderSummary(body.result.summary); renderTraces(body.result.traces); renderChart(state.bars, body.result.traces); $('#results-section').scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (error) { showError(error.message); } finally { button.disabled = false; button.textContent = '确认并运行实验'; }
}

async function load() {
  $('#api-endpoint').textContent = apiBase.replace(/^https?:\/\//, '');
  try { state.dataset = await request('/v1/datasets/demo'); state.bars = (await request('/v1/datasets/demo/bars')).bars; renderDataset(); } catch (error) { $('#connection').textContent = 'API 未连接'; showError(`无法连接 API：${error.message}`); }
}

$('#strategy-prompt').addEventListener('input', updatePromptCount); $('#generate-button').addEventListener('click', generateDraft); $('#run-button').addEventListener('click', confirmRun); $('#confirm-checkbox').addEventListener('change', () => { if (state.selectedCandidate) selectCandidate(state.selectedCandidate); });
$$('[data-prompt]').forEach((button) => button.addEventListener('click', () => { $('#strategy-prompt').value = button.dataset.prompt; updatePromptCount(); $('#strategy-prompt').focus(); }));
updatePromptCount(); load();

