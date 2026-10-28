const params = new URLSearchParams(window.location.search);
const apiBase = (params.get('api') || 'http://127.0.0.1:8000').replace(/\/$/, '');
const state = { dataset: null, bars: [], run: null };

const $ = (selector) => document.querySelector(selector);

function showError(message) {
  const error = $('#error');
  error.hidden = false;
  error.textContent = message;
}

function clearError() {
  $('#error').hidden = true;
  $('#error').textContent = '';
}

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body);
    throw new Error(`${response.status}: ${detail}`);
  }
  return body;
}

function condition(type, period) { return { type, period: Number(period) }; }

function strategyPayload() {
  const form = new FormData($('#strategy-form'));
  return {
    version_id: form.get('version_id'),
    entry_condition: condition(form.get('entry_type'), form.get('entry_period')),
    exit_condition: condition(form.get('exit_type'), form.get('exit_period')),
    position_fraction: Number(form.get('position_fraction')),
    lot_size: Number(form.get('lot_size')),
    confirmed: form.get('confirmed') === 'on',
  };
}

function setFeedback(message, kind = '') {
  const feedback = $('#rule-feedback');
  feedback.textContent = message;
  feedback.className = `feedback ${kind}`;
}

function renderDataset() {
  const data = state.dataset;
  $('#connection').textContent = 'API 已连接';
  $('#connection').classList.add('ok');
  $('#dataset-note').textContent = `${data.symbol} · ${data.bar_count} 根可见日线`;
  $('#research-range').textContent = `${data.research_start}—${data.research_end}`;
  $('#holdout-range').textContent = `${data.holdout_start}—${data.holdout_end}`;
}

function metric(label, value) { return `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`; }

function renderSummary(summary) {
  $('#summary').className = 'summary-grid';
  $('#summary').innerHTML = [
    metric('状态', summary.status), metric('交易数', summary.trade_count),
    metric('期末权益', summary.final_equity), metric('总收益', summary.total_return),
    metric('已实现盈亏', summary.realized_pnl), metric('未成交订单', summary.not_filled_order_count),
  ].join('');
}

function statusClass(status) { return status === 'PASS' ? 'status-pass' : status === 'FAIL' ? 'status-fail' : 'status-unavailable'; }

function traceReason(trace) {
  const entry = trace.condition_results.entry;
  const exit = trace.condition_results.exit;
  const parts = [`入场：${entry.reason}`, `退出：${exit.reason}`];
  if (trace.order_attempt) {
    const order = trace.order_attempt;
    parts.push(order.status === 'FILLED' ? `${order.side === 'buy' ? '买入' : '卖出'}成交 ${order.price}` : `未成交：${order.reason}`);
  }
  if (trace.warnings?.length) parts.push(trace.warnings.join('、'));
  return parts.join('；');
}

function renderTraces(traces) {
  const table = $('#trace-table');
  table.replaceChildren();
  for (const trace of traces) {
    const row = document.createElement('tr');
    const entry = trace.condition_results.entry;
    const exit = trace.condition_results.exit;
    const order = trace.order_attempt;
    row.innerHTML = `<td><code>${trace.date}</code></td><td class="${statusClass(entry.status)}">${entry.status}</td><td class="${statusClass(exit.status)}">${exit.status}</td><td>${trace.signal || '—'}</td><td>${order ? `${order.status}${order.price ? ` @ ${order.price}` : ''}` : '—'}</td><td>${traceReason(trace)}</td>`;
    table.appendChild(row);
  }
}

function svgElement(name, attrs = {}) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

function renderChart(bars, traces) {
  const svg = $('#chart');
  svg.replaceChildren();
  if (!bars.length) return;
  const width = 900; const height = 300; const pad = { left: 48, right: 18, top: 24, bottom: 38 };
  const closes = bars.map((bar) => Number(bar.close));
  const min = Math.min(...closes); const max = Math.max(...closes); const range = max - min || 1;
  const x = (index) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, bars.length - 1));
  const y = (value) => pad.top + (max - value) * ((height - pad.top - pad.bottom) / range);
  for (let i = 0; i < 4; i += 1) {
    const value = min + range * (i / 3);
    svg.appendChild(svgElement('line', { x1: pad.left, x2: width - pad.right, y1: y(value), y2: y(value), class: 'chart-grid' }));
    const label = svgElement('text', { x: 8, y: y(value) + 4, class: 'chart-label' }); label.textContent = value.toFixed(2); svg.appendChild(label);
  }
  svg.appendChild(svgElement('polyline', { points: closes.map((value, index) => `${x(index)},${y(value)}`).join(' '), class: 'chart-line' }));
  bars.forEach((bar, index) => { const label = svgElement('text', { x: x(index), y: height - 13, class: 'chart-label', 'text-anchor': 'middle' }); label.textContent = bar.date.slice(4); svg.appendChild(label); });
  const byDate = new Map(traces.map((trace) => [trace.date, trace]));
  bars.forEach((bar, index) => {
    const trace = byDate.get(bar.date); if (!trace) return;
    const markers = []; if (trace.signal === 'entry') markers.push(['mark-entry', -12]); if (trace.signal === 'exit') markers.push(['mark-exit', 12]); if (trace.order_attempt?.status === 'FILLED') markers.push(['mark-fill', 0]);
    markers.forEach(([className, offset]) => svg.appendChild(svgElement('circle', { cx: x(index), cy: y(Number(bar.close)) + offset, r: 6, class: className })));
  });
}

async function load() {
  try {
    state.dataset = await request('/v1/datasets/demo');
    state.bars = (await request('/v1/datasets/demo/bars')).bars;
    renderDataset(); renderChart(state.bars, []);
  } catch (error) { $('#connection').textContent = 'API 未连接'; showError(error.message); }
}

async function validate() {
  clearError();
  try { const body = await request('/v1/strategies/validate', { method: 'POST', body: JSON.stringify(strategyPayload()) }); setFeedback(body.confirmation_required ? '规则结构有效；勾选确认后才能运行。' : '规则已确认，可以运行。', 'ok'); }
  catch (error) { setFeedback('规则检查失败。', 'error'); showError(error.message); }
}

async function run() {
  clearError(); const button = $('#run-button'); button.disabled = true;
  try {
    const body = await request('/v1/runs', { method: 'POST', body: JSON.stringify({ dataset_id: 'demo-synthetic', strategy: strategyPayload() }) });
    state.run = body.result; $('#run-id').textContent = body.run_id; renderSummary(body.result.summary); renderTraces(body.result.traces); renderChart(state.bars, body.result.traces); setFeedback('运行完成；解释来自本次运行记录。', 'ok');
  } catch (error) { showError(error.message); } finally { button.disabled = false; }
}

$('#validate-button').addEventListener('click', validate);
$('#strategy-form').addEventListener('submit', (event) => { event.preventDefault(); run(); });
load();

