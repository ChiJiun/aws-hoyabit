/**
 * render_live.mjs — 以真實 run 輸出驗證前端渲染
 *
 * 用途：拿 outputs/ 下實際跑出來的 report_data.json / evidence_list.json / report.md
 *       在 Node 中執行 index.html 的渲染函式，確認每個章節都能產出內容。
 *
 * 執行：node frontend/tests/render_live.mjs [runDir]
 *       未指定 runDir 時自動取 outputs/ 下最新的 run_* 目錄。
 */

import { readFileSync, readdirSync, statSync, existsSync } from 'fs';
import { resolve, dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = resolve(__dirname, '..');
const ROOT = resolve(FRONTEND_DIR, '..');

/* ---- 找出要驗證的 run 目錄 ---- */
function latestRun() {
  const out = join(ROOT, 'outputs');
  if (!existsSync(out)) return null;
  const dirs = readdirSync(out)
    .filter(d => d.startsWith('run_'))
    .map(d => ({ d, p: join(out, d) }))
    .filter(x => statSync(x.p).isDirectory())
    .filter(x => existsSync(join(x.p, 'report_data.json')))
    .sort((a, b) => statSync(b.p).mtimeMs - statSync(a.p).mtimeMs);

  // 中止或失敗的執行會留下空的 report_data，挑到它會誤報失敗。
  // 優先取最新一次「有實際分析內容」的執行。
  for (const x of dirs) {
    try {
      const rd = JSON.parse(readFileSync(join(x.p, 'report_data.json'), 'utf8'));
      if (Array.isArray(rd.dimensions) && rd.dimensions.length) return x.p;
    } catch (e) { /* 檔案損壞則跳過 */ }
  }
  return dirs.length ? dirs[0].p : null;
}

const runDir = process.argv[2] ? resolve(process.argv[2]) : latestRun();
if (!runDir) {
  console.error('找不到含 report_data.json 的 run 目錄，請先執行一次分析。');
  process.exit(1);
}
console.log(`驗證來源：${runDir}\n`);

const rd = JSON.parse(readFileSync(join(runDir, 'report_data.json'), 'utf8'));
const evl = existsSync(join(runDir, 'evidence_list.json'))
  ? JSON.parse(readFileSync(join(runDir, 'evidence_list.json'), 'utf8')) : [];
const reportText = existsSync(join(runDir, 'report.md'))
  ? readFileSync(join(runDir, 'report.md'), 'utf8') : '';

/* ---- 載入前端腳本 ---- */
const html = readFileSync(join(FRONTEND_DIR, 'index.html'), 'utf8');
const m = html.match(/<script>\s*\r?\n([\s\S]*?)<\/script>/);
if (!m) { console.error('無法取出 index.html 的 <script>'); process.exit(1); }

function makeEl() {
  return {
    innerHTML: '', textContent: '', value: '', href: '', hidden: false,
    style: {}, dataset: {}, disabled: false, open: false,
    classList: { add() { }, remove() { }, contains: () => false },
    addEventListener() { }, appendChild() { }, scrollIntoView() { },
    setAttribute() { }, getAttribute: () => null, removeAttribute() { },
    querySelector: () => null, querySelectorAll: () => [], closest: () => null, focus() { }
  };
}
class ImageStub {
  set src(v) { if (typeof this.onerror === 'function') this.onerror(); }
}
const cache = new Map();
const g = {
  Image: ImageStub,
  document: {
    getElementById(id) { if (!cache.has(id)) cache.set(id, makeEl()); return cache.get(id); },
    querySelector: () => null, querySelectorAll: () => []
  },
  location: { hostname: 'localhost', origin: 'http://localhost:8080', protocol: 'http:', href: 'http://localhost:8080/' },
  window: { scrollTo() { }, matchMedia: () => ({ matches: false }) },
  fetch: async () => ({ ok: false, status: 500, json: async () => ({}), text: async () => '' }),
  marked: { parse: md => `<p>${md}</p>` },
  Chart: undefined,
  URL: Object.assign(globalThis.URL, { createObjectURL: () => 'blob:stub' }),
  Blob: class { constructor() { } },
  setInterval: () => 0, clearInterval: () => { },
  setTimeout: fn => { if (typeof fn === 'function') fn(); return 0; },
  IntersectionObserver: undefined
};
const EX = ['secVerdict', 'secSignals', 'secDimensions', 'secTyped', 'secCharts',
  'secReasoning', 'secEvidence', 'secCoverage', 'secWatchlist', 'secRaw'];
const names = Object.keys(g);
const api = new Function(...names,
  `${m[1]}\n;return { ${EX.join(', ')}, __setEvidence(v){ evidenceList = v; } };`
)(...names.map(n => g[n]));
api.__setEvidence(evl);

/* ---- 渲染每個章節 ---- */
const req = { symbols: rd.symbols, question: '（來自實際執行的分析題目）' };
const sections = {
  '1 判斷': api.secVerdict(rd, req, rd.symbols, rd.question_type),
  '2 異常訊號': api.secSignals(rd),
  '3 分析維度': api.secDimensions(rd, rd.symbols),
  '4 題型專屬': api.secTyped(rd, rd.question_type, rd.symbols),
  '5 圖表': api.secCharts(rd),
  '6 推理鏈': api.secReasoning(reportText),
  '7 證據溯源': api.secEvidence(),
  '8 資料覆蓋': api.secCoverage(rd),
  '9 後續觀察': api.secWatchlist(rd),
  '10 原始交付物': api.secRaw(reportText, rd)
};

let empty = [];
for (const [name, htmlOut] of Object.entries(sections)) {
  const status = htmlOut ? 'OK   ' : 'EMPTY';
  if (!htmlOut) empty.push(name);
  console.log(`${status} ${name.padEnd(14)} ${String(htmlOut.length).padStart(7)} chars`);
}

const all = Object.values(sections).join('');
const count = re => (all.match(re) || []).length;

console.log('\n--- 渲染產物統計 ---');
console.log('canvas（圖表）      :', count(/<canvas/g));
console.log('證據 chip           :', count(/class="chip"/g));
console.log('details 收折        :', count(/<details/g));
console.log('紅色訊號            :', count(/sig red/g));
console.log('黃色訊號            :', count(/sig yellow/g));
console.log('na 維度             :', count(/dim na/g));

console.log('\n--- 安全與正確性 ---');
const leaked = ['[VERDICT]', '[DIM]', '[SIGNAL]', '[COVERAGE]', '[WATCHLIST]', '[CHECKED_NORMAL]']
  .filter(k => all.includes(k));
console.log('C7 標記洩漏         :', leaked.length ? leaked.join(', ') : 'none');
const scriptTags = count(/<script/g);
console.log('未逸出 script 標籤  :', scriptTags);

let fail = 0;
const check = (cond, msg) => { console.log(`${cond ? 'ok  ' : 'FAIL'} ${msg}`); if (!cond) fail++; };
console.log('');
check(empty.length === 0, `所有章節皆有內容${empty.length ? '（空：' + empty.join(', ') + '）' : ''}`);
check(leaked.length === 0, 'report.md 的 C7 標記未洩漏到畫面');
check(scriptTags === 0, '渲染結果不含未逸出的 script 標籤');
check(count(/<canvas/g) > 0, '至少渲染一張圖表');
check(count(/class="chip"/g) > 0, '證據引用可點擊');
check(sections['7 證據溯源'].includes('content_reference'), '證據區提供 content_reference 供抽查');

console.log(`\n${'='.repeat(52)}`);
if (fail) { console.log(`${fail} 項未通過`); process.exit(1); }
console.log('實際資料渲染驗證通過');
