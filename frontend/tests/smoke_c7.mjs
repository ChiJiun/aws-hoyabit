/**
 * Smoke test — C7 結構化報告渲染
 *
 * 不依賴建置工具或 jsdom：以最小 DOM stub 在 Node 中實際執行 index.html 內的
 * 渲染函式，驗證它們對 fixture 與各種畸形輸入的行為。
 *
 * 執行：node frontend/tests/smoke_c7.mjs
 */

import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = resolve(__dirname, '..');

const fx = name => JSON.parse(readFileSync(resolve(FRONTEND_DIR, `fixtures/${name}`), 'utf8'));
const fixSingle = fx('c7_single_integration.json');
const fixHypo = fx('c7_hypothesis.json');
const fixCmp = fx('c7_comparison.json');

const html = readFileSync(resolve(FRONTEND_DIR, 'index.html'), 'utf8');
const scriptMatch = html.match(/<script>\s*\r?\n([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  console.error('FAIL: 無法從 index.html 取出 <script> 內容');
  process.exit(1);
}
const script = scriptMatch[1];

let passed = 0, failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; console.log(`  ok   ${msg}`); }
  else { failed++; console.error(`  FAIL ${msg}`); }
}

/* ===================== 最小 DOM stub ===================== */
function makeEl() {
  const el = {
    innerHTML: '', textContent: '', value: '', href: '', hidden: false,
    style: {}, dataset: {}, disabled: false, open: false,
    classList: { add() { }, remove() { }, contains: () => false },
    addEventListener() { }, appendChild() { }, scrollIntoView() { },
    setAttribute() { }, getAttribute: () => null, removeAttribute() { },
    querySelector: () => null, querySelectorAll: () => [],
    closest: () => null, focus() { }
  };
  return el;
}
const elCache = new Map();
const documentStub = {
  getElementById(id) {
    if (!elCache.has(id)) elCache.set(id, makeEl());
    return elCache.get(id);
  },
  querySelector: () => null,
  querySelectorAll: () => []
};

const sandboxGlobals = {
  document: documentStub,
  location: { hostname: 'localhost', origin: 'http://localhost:8080', protocol: 'http:', href: 'http://localhost:8080/' },
  window: { scrollTo() { }, matchMedia: () => ({ matches: false }) },
  fetch: async () => ({ ok: false, status: 500, json: async () => ({}), text: async () => '' }),
  marked: { parse: md => `<p>${md}</p>` },
  Chart: undefined,
  URL: Object.assign(globalThis.URL, { createObjectURL: () => 'blob:stub' }),
  Blob: globalThis.Blob ?? class { constructor() { } },
  setInterval: () => 0,
  clearInterval: () => { },
  setTimeout: (fn) => { if (typeof fn === 'function') fn(); return 0; },
  IntersectionObserver: undefined
};

const EXPORTS = [
  'esc', 'num', 'fmt', 'compact', 'shortId', 'sourceLabel', 'verifyLinks',
  'normPoints', 'cell', 'inferType', 'splitReport', 'linkCitations', 'mdToHtml',
  'secVerdict', 'secSignals', 'secDimensions', 'secTyped', 'secHypothesis',
  'secComparison', 'secConsistency', 'secCharts', 'secReasoning', 'secEvidence',
  'secCoverage', 'secWatchlist', 'secRaw', 'chips', 'needsSecondAxis', 'safeJson',
  'metricRows', 'dimensionOverview', 'isExtreme', 'percentileTag', 'chartPlan', 'hasSeries'
];

let api;
try {
  const names = Object.keys(sandboxGlobals);
  const body = `${script}\n;return { ${EXPORTS.join(', ')}, __setEvidence(v){ evidenceList = v; } };`;
  api = new Function(...names, body)(...names.map(n => sandboxGlobals[n]));
} catch (err) {
  console.error('FAIL: 無法在 sandbox 中執行前端腳本 —', err.message);
  process.exit(1);
}

const REQ = { symbols: ['BTC'], question: '分析 BTC 目前市場狀態' };

/* ===================== 1. 逸出與注入防護 ===================== */
console.log('\n[1] HTML 逸出與注入防護');
{
  assert(api.esc('<script>x</script>') === '&lt;script&gt;x&lt;/script&gt;', 'esc 逸出角括號');
  assert(api.esc(`a"b'c&d`) === 'a&quot;b&#39;c&amp;d', 'esc 逸出引號與 &');
  assert(api.esc(null) === '' && api.esc(undefined) === '', 'esc 處理 null/undefined');

  const evil = '<img src=x onerror=alert(1)>';
  const rd = {
    ...fixSingle,
    verdict: { ...fixSingle.verdict, text: evil, invalidation: evil }
  };
  const out = api.secVerdict(rd, { symbols: ['BTC'], question: evil }, ['BTC'], 'single_integration');
  assert(!out.includes('<img src=x'), '判斷區塊逸出惡意 HTML');
  assert(out.includes('&lt;img'), '惡意 HTML 以逸出形式呈現');
}

/* ===================== 2. 題型路由 ===================== */
console.log('\n[2] 題型路由');
{
  assert(api.inferType({ symbols: ['BTC', 'ETH'], question: 'x' }) === 'comparison', '兩個幣種 → comparison');
  assert(api.inferType({ symbols: ['BTC'], question: '市場認為會盤整' }) === 'hypothesis', '假設關鍵詞 → hypothesis');
  assert(api.inferType({ symbols: ['BTC'], question: '分析近況' }) === 'single_integration', '預設 → single_integration');

  const h = api.secTyped(fixHypo, 'hypothesis', ['ETH']);
  assert(h.includes('假設檢驗') && h.includes('支持證據') && h.includes('反對證據'), 'hypothesis 題型渲染正反欄');
  const c = api.secTyped(fixCmp, 'comparison', ['BTC', 'ETH']);
  assert(c.includes('逐維度比較') && c.includes('<table'), 'comparison 題型渲染比較表');
  const s = api.secTyped(fixSingle, 'single_integration', ['BTC']);
  assert(s.includes('跨來源一致性'), 'single_integration 題型渲染一致性分組');
  assert(!s.includes('假設檢驗') && !s.includes('逐維度比較'), 'single_integration 不誤渲染其他題型版面');
}

/* ===================== 3. C7 缺失時的降級 ===================== */
console.log('\n[3] C7 缺失／畸形時降級不拋錯');
{
  const bad = [null, undefined, 'string', 42, {}, { verdict: null }, { dimensions: 'x', signals: 'y' }];
  let threw = false;
  for (const rd of bad) {
    try {
      api.secVerdict(rd, REQ, ['BTC'], 'single_integration');
      api.secSignals(rd);
      api.secDimensions(rd, ['BTC']);
      api.secTyped(rd, 'single_integration', ['BTC']);
      api.secCharts(rd);
      api.secCoverage(rd);
      api.secWatchlist(rd);
    } catch (e) { threw = true; console.error('    →', e.message); }
  }
  assert(!threw, '所有畸形 report_data 皆不拋出例外');
  assert(api.secSignals(null) === '', 'null → 訊號區塊留空');
  assert(api.secDimensions(null, ['BTC']) === '', 'null → 維度區塊留空');
  assert(api.secCoverage({}) === '', '無 coverage → 區塊留空');

  // verdict 缺失時仍要產出區塊並提示改看報告
  const v = api.secVerdict(null, REQ, ['BTC'], 'single_integration');
  assert(v.includes('sec-verdict'), 'verdict 缺失仍渲染判斷區塊');
  assert(v.includes('完整報告'), 'verdict 缺失時引導使用者看完整報告');
}

/* ===================== 4. coverage 60 邊界 ===================== */
console.log('\n[4] coverage < 60 觸發資料可用性警示');
{
  const low = api.secCoverage({ coverage: { pct: 59, got: ['a'], missing: [{ capability: 'b', reason: 'timeout' }] } });
  assert(low.includes('cov-warn'), 'pct 59 → 顯示警示');
  assert(low.includes('不會自動改寫模型結論'), '警示明確聲明不改寫結論');
  const ok60 = api.secCoverage({ coverage: { pct: 60, got: ['a'], missing: [] } });
  assert(!ok60.includes('cov-warn'), 'pct 60 → 不顯示警示（邊界）');
  const ok86 = api.secCoverage(fixSingle);
  assert(!ok86.includes('cov-warn'), 'pct 86 → 不顯示警示');

  const nul = api.secCoverage({ coverage: { pct: null, got: [], missing: [{ capability: 'x', reason: 'y' }] } });
  assert(nul.includes('--'), 'pct null → 顯示 -- 而非 0 或 100');
  assert(!nul.includes('>0%<'), 'pct null 不以 0% 代替');

  assert(low.includes('timeout'), 'missing 項目顯示原因');
}

/* ===================== 5. 維度 state=na ===================== */
console.log('\n[5] 維度 state=na 明示無資料');
{
  const out = api.secDimensions(fixSingle, ['BTC']);
  assert(out.includes('無資料'), 'na 維度顯示「無資料」標籤');
  assert(out.includes('dim na'), 'na 維度套用專屬樣式');
  assert(out.includes('總經環境'), 'na 維度仍列出名稱，未靜默隱藏');
  assert(out.includes('項無資料'), '區塊標頭統計無資料維度數');
}

/* ===================== 6. 圖表資料防護 ===================== */
console.log('\n[6] series 資料防護');
{
  assert(api.secCharts({ series: null }) === '', 'series null → 不渲染圖表區');
  assert(api.secCharts({ series: {} }) === '', 'series 空物件 → 不渲染');
  assert(api.secCharts({ series: { price: { BTC: [] } } }) === '', '空點陣列 → 不渲染');
  assert(api.secCharts({ series: { price: { BTC: [['2026-01-01', 1]] } } }) === '', '單一資料點 → 不渲染');
  const good = api.secCharts(fixSingle);
  assert(good.includes('<canvas'), '有效 series → 渲染 canvas');
  assert(good.includes('前端僅負責呈現'), '圖表區聲明數值由後端計算');

  assert(api.needsSecondAxis({ BTC: [['d', 100000]], ETH: [['d', 3000]] }) === true, '數量級差距大 → 雙 Y 軸');
  assert(api.needsSecondAxis({ BTC: [['d', 100]], ETH: [['d', 110]] }) === false, '數量級相近 → 單 Y 軸');
}

/* ===================== 7. hypothesis 兩種資料形狀 ===================== */
console.log('\n[7] hypothesis／comparison 同時支援兩種後端形狀');
{
  // fixture 形狀：物件陣列
  const objShape = api.normPoints([{ point: 'A', strength: 'strong', evidence_ids: ['ev_1'] }]);
  assert(objShape.length === 1 && objShape[0].text === 'A' && objShape[0].strength === 'strong', '物件形狀正確解析');
  // 實際解析器形狀：字串陣列
  const strShape = api.normPoints(['甲', '乙']);
  assert(strShape.length === 2 && strShape[0].text === '甲' && strShape[0].ids.length === 0, '字串形狀正確解析');
  assert(api.normPoints(null).length === 0 && api.normPoints('x').length === 0, '非陣列輸入回傳空陣列');

  const liveHypo = {
    hypothesis: {
      statement: 'S', supporting: ['支持一', '支持二'], opposing: ['反對一'], verdict_reason: 'R'
    }
  };
  const out = api.secHypothesis(liveHypo);
  assert(out.includes('支持一') && out.includes('反對一') && out.includes('R'), '字串形狀可完整渲染');

  // comparison rows 的 a/b 可能是空物件
  assert(api.cell({}).value === '' && api.cell(null).value === '', '空 a/b 安全取值');
  const liveCmp = {
    comparison: {
      rows: [{ dimension: '價格', a: {}, b: {}, edge: 'A' }],
      when_prefer_a: 'X', when_prefer_b: 'Y'
    }
  };
  const cout = api.secComparison(liveCmp, ['BTC', 'ETH']);
  assert(cout.includes('價格') && cout.includes('--'), '空 a/b 以 -- 呈現而非崩潰');
  assert(cout.includes('class="win"') || cout.includes('win'), 'edge 側套用高亮');
}

/* ===================== 8. 證據可回溯性 ===================== */
console.log('\n[8] 證據可回溯性呈現');
{
  api.__setEvidence([]);
  assert(api.secEvidence().includes('未取得證據清單'), '無證據時顯示明確說明');

  api.__setEvidence([{
    evidence_id: 'ev_abc123',
    source: 'https://api.binance.com/api/v3/klines?symbol=BTCUSDT',
    fetched_at: '2026-08-02T01:00:00Z',
    content_reference: { endpoint: 'https://api.binance.com/api/v3/klines', pair: 'BTCUSDT', human_url: 'https://www.binance.com/en/trade/BTC_USDT' },
    related_claim: '檢驗近期價格方向'
  }]);
  const out = api.secEvidence();
  assert(out.includes('ev_abc123'), '顯示 evidence_id');
  assert(out.includes('2026-08-02T01:00:00Z'), '顯示 fetched_at');
  assert(out.includes('檢驗近期價格方向'), '顯示 related_claim');
  assert(out.includes('BTCUSDT'), 'content_reference 內容可查閱');
  assert(out.includes('<details'), 'content_reference 以原生可鍵盤操作的 details 收折');
  assert(out.includes('www.binance.com'), '優先提供人類可讀查證連結');

  const links = api.verifyLinks({ human_url: 'https://a.com', items: [{ url: 'https://b.com', title: 'T' }] });
  assert(links.length === 2, 'verifyLinks 蒐集 human_url 與 items');
  assert(api.verifyLinks({ human_url: 'javascript:alert(1)' }).length === 0, 'verifyLinks 拒絕非 http(s) 協定');
  assert(api.verifyLinks(null).length === 0, 'verifyLinks 處理 null');

  // 報告文字中的 evidence_id 應轉為可點擊 chip
  const linked = api.linkCitations('依據 ev_abc123 顯示');
  assert(linked.includes('data-ev="ev_abc123"'), '報告內引用轉為可點擊 chip');
}

/* ===================== 9. 推理鏈三層分離 ===================== */
console.log('\n[9] 推理鏈事實→推論→結論分層');
{
  const md = '## 市場判斷\n判斷內容\n\n## 關鍵依據\n依據內容\n\n## 信心說明\n限制內容\n';
  const parts = api.splitReport(md);
  assert(parts['市場判斷'] === '判斷內容', '解析市場判斷章節');
  assert(parts['關鍵依據'] === '依據內容', '解析關鍵依據章節');
  assert(parts['信心說明'] === '限制內容', '解析信心說明章節');

  const out = api.secReasoning(md);
  assert(out.includes('事實層') && out.includes('推論與結論層') && out.includes('校準層'), '三層皆標示');
  const iFact = out.indexOf('事實層'), iInfer = out.indexOf('推論與結論層'), iCal = out.indexOf('校準層');
  assert(iFact < iInfer && iInfer < iCal, '三層依事實→推論→校準順序呈現');
  assert(api.secReasoning('') === '', '無報告內容 → 區塊留空');
  assert(api.secReasoning('沒有章節標題的純文字') === '', '無可辨識章節 → 區塊留空');
}

/* ===================== 10. 不提供投資建議 ===================== */
console.log('\n[10] 資訊提煉定位');
{
  const out = api.secVerdict(fixSingle, REQ, ['BTC'], 'single_integration');
  assert(out.includes('不提供任何投資建議'), '判斷區塊明示不提供投資建議');
  assert(html.includes('不提供投資建議'), '輸入頁即聲明定位');
  // 只攔截「肯定式建議」語法；免責聲明會以否定語境提及這些詞，不應誤判
  const advicePatterns = [
    /建議(買進|賣出|持有|加倉|減倉|進場|出場)/,
    /目標價\s*[為是:：]/,
    /(應該?|可以)(買進|賣出|進場|出場)/
  ];
  const offenders = advicePatterns.filter(re => re.test(html)).map(re => re.source);
  assert(offenders.length === 0, `前端文案不含肯定式投資建議${offenders.length ? '：' + offenders.join(' , ') : ''}`);
  assert(/不提供[^。]*投資建議/.test(html), '免責聲明以否定語境明示不提供投資建議');
}

/* ===================== 11. 無障礙與動效偏好 ===================== */
console.log('\n[11] 無障礙與動效偏好');
{
  assert(html.includes('prefers-reduced-motion:reduce'), 'CSS 支援 prefers-reduced-motion');
  assert(html.includes('aria-pressed'), '幣種按鈕使用 aria-pressed');
  assert(html.includes('role="alert"') && html.includes('aria-live'), '錯誤與進度使用 aria-live');
  assert(html.includes(':focus-visible'), '提供鍵盤焦點樣式');
  assert(html.includes('aria-label="報告章節導覽"'), '章節導覽有無障礙標籤');
  assert(html.includes('lang="zh-Hant"'), '宣告正確語言');
  const signalsOut = api.secSignals(fixSingle);
  assert(signalsOut.includes('aria-hidden="true"'), '裝飾性符號對輔助技術隱藏');
  assert(!/<div class="chip"/.test(signalsOut), '證據 chip 使用 button 而非 div，確保可鍵盤操作');
}

/* ===================== 12. checked_normal 全面掃描證明 ===================== */
console.log('\n[12] 已檢查正常項目');
{
  const out = api.secSignals(fixSingle);
  assert(out.includes('已檢查並確認落在常態範圍'), '呈現 checked_normal 區塊');
  assert(out.includes('全面掃描'), '說明用途為證明掃描完整性');
  const noSig = api.secSignals({ signals: [], checked_normal: ['一切正常'] });
  assert(noSig.includes('未偵測到達門檻的異常訊號'), '無異常時明確說明而非留白');
  assert(noSig.includes('而非我們沒有檢查'), '無異常時強調已檢查');
  assert(api.secSignals({ signals: [], checked_normal: [] }) === '', '兩者皆空 → 區塊留空');
}

/* ===================== 13. 響應式 ===================== */
console.log('\n[13] 響應式版面');
{
  assert(html.includes('@media(max-width:760px)'), '有窄螢幕斷點');
  assert(/@media\(max-width:760px\)[\s\S]*?hyp-cols[\s\S]*?grid-template-columns:1fr/.test(html), '窄螢幕時正反欄改為單欄');
  assert(html.includes('@media(max-width:1000px)'), '有中等螢幕斷點');
  assert(html.includes('overflow-x:auto'), '比較表在窄螢幕可水平捲動');
}

/* ===================== 14. 指標百分位視覺化 ===================== */
console.log('\n[14] 指標百分位視覺化');
{
  // 後端填充的形狀：{key: {value, label, percentile}}
  const enriched = {
    ...fixSingle,
    dimensions: [{
      name: '價格動能', state: 'weak', headline: 'h', evidence_ids: [],
      per_symbol: {
        BTC: {
          volume_zscore: { value: -2.21, label: '成交量 Z-score', percentile: 0.3 },
          adx: { value: 22.19, label: 'ADX 趨勢強度', percentile: 15.9 },
          rsi_14: { value: 52, label: 'RSI 14', percentile: 50 }
        }
      }
    }, {
      name: '槓桿結構', state: 'neutral', headline: 'h2', evidence_ids: [],
      per_symbol: { BTC: { funding_rate: { value: 0.0001, label: '資金費率' } } }
    }]
  };
  const out = api.secDimensions(enriched, ['BTC']);
  assert(out.includes('ptrack'), '有百分位者渲染百分位軌道');
  assert(out.includes('成交量 Z-score'), '使用後端提供的中文標籤');
  assert(out.includes('mark extreme'), 'P0.3 標記為極端值');
  assert(out.includes('歷史低位 P0'), '極端低位標示文字');
  assert(out.includes('歷史低位 P16') && !out.includes('歷史高位 P16'), 'P15.9 標為低位而非高位');
  assert(out.includes('P50') && !out.includes('歷史高位 P50'), 'P50 顯示為一般百分位');
  assert(out.includes('資金費率'), '無百分位的指標仍顯示數值');

  // 相容 fixture 的純量形狀
  const scalarShape = {
    ...fixSingle,
    dimensions: [{ name: 'D', state: 'strong', headline: 'h', evidence_ids: [], per_symbol: { BTC: { rsi_14: 55 } } }]
  };
  const s2 = api.secDimensions(scalarShape, ['BTC']);
  assert(s2.includes('55'), '純量形狀仍可渲染');
  assert(!s2.includes('ptrack'), '純量無百分位時不畫軌道');

  assert(api.isExtreme(85) && api.isExtreme(10), '>=80 或 <=20 判定為極端');
  assert(!api.isExtreme(50) && !api.isExtreme(null), '中間值與 null 不判為極端');
}

/* ===================== 15. 維度狀態總覽 ===================== */
console.log('\n[15] 維度狀態總覽');
{
  const out = api.secDimensions(fixSingle, ['BTC']);
  assert(out.includes('dim-overview'), '渲染維度總覽');
  assert(out.includes('ov-axis'), '總覽含狀態軸');
  assert(out.includes('偏弱') && out.includes('偏強'), '總覽標示方向兩端');
  assert(out.includes('存在背離'), '說明同時偏強偏弱代表背離');
  // 單一維度時不需要總覽
  const one = { ...fixSingle, dimensions: [fixSingle.dimensions[0]] };
  assert(!api.secDimensions(one, ['BTC']).includes('dim-overview'), '只有一個維度時不顯示總覽');
}

/* ===================== 16. 訊號強度總覽 ===================== */
console.log('\n[16] 訊號強度總覽');
{
  const out = api.secSignals(fixSingle);
  assert(out.includes('sig-summary'), '渲染訊號統計');
  assert(out.includes('強烈異常') && out.includes('值得注意') && out.includes('已檢查正常'), '三類計數皆呈現');
  const noneOut = api.secSignals({ signals: [], checked_normal: ['x', 'y'] });
  assert(noneOut.includes('sig-summary'), '無異常時仍顯示統計（0 也是資訊）');
}

/* ===================== 17. 組合圖表 ===================== */
console.log('\n[17] 跨來源組合圖表');
{
  const series = {
    price: { BTC: [['2026-07-01', 100], ['2026-07-02', 101], ['2026-07-03', 102]] },
    volume: { BTC: [['2026-07-01', 10], ['2026-07-02', 12], ['2026-07-03', 9]] },
    fear_greed: { MARKET: [['2026-07-01', 30], ['2026-07-02', 28], ['2026-07-03', 27]] }
  };
  const plan = api.chartPlan({ series });
  const ids = plan.map(p => p.id);
  assert(ids.includes('combo-pv'), '價格與成交量組成一張圖');
  assert(ids.includes('combo-ps'), '價格與情緒組成一張圖');
  assert(!ids.includes('s-volume'), '已併入組合圖的 series 不重複單獨出圖');
  assert(!ids.includes('s-fear_greed'), '情緒併入組合圖後不重複出圖');

  const out = api.secCharts({ series });
  assert(out.includes('量價是否同步'), '組合圖說明它要回答什麼問題');
  assert(out.includes('情緒與價格是否脫鉤'), '情緒疊圖說明背離判讀方式');
  assert((out.match(/<canvas/g) || []).length === plan.length, 'canvas 數與圖表計畫一致');

  // 只有價格時退回單圖
  const onlyPrice = api.chartPlan({ series: { price: series.price } });
  assert(onlyPrice.length === 1 && onlyPrice[0].id === 's-price', '只有價格時渲染單一價格圖');
  assert(api.chartPlan({ series: {} }).length === 0, '無 series 時無圖表計畫');
}

/* ===================== 18. 金寶載入動畫 ===================== */
console.log('\n[18] 金寶載入畫面');
{
  assert(html.includes('class="mascot"'), '含吉祥物元素');
  assert(/aria-label="吉祥物金寶正在奔跑蒐集資料"/.test(html), '吉祥物提供無障礙描述');
  assert(html.includes('金寶'), '標示吉祥物名稱');
  assert(/@keyframes hop/.test(html) && /@keyframes stride/.test(html), '含彈跳與跨步動畫');
  assert(html.includes('#ff8c3d') || html.includes('#ff9a4f'), '使用橘色毛色');
  assert(html.includes('#1b1b1f'), '使用黑色條紋');
  // 計時器移到右上角
  assert(html.includes('class="load-timer"'), '載入畫面含計時器');
  assert(/\.load-timer\{position:absolute;top:[^;]+;right:/.test(html), '計時器定位於右上角');
  assert(/id="elapsed"/.test(html), '計時器保留 elapsed 元素供 JS 更新');
  // 全螢幕置中
  assert(/#loading\{display:none;position:fixed;inset:0/.test(html), '載入畫面為全螢幕覆蓋');
  assert(html.includes('justify-content:center'), '內容置中');
  assert(html.includes('load-steps'), '含階段進度指示');
}

/* ===================== SUMMARY ===================== */
console.log(`\n${'='.repeat(56)}`);
console.log(`結果：${passed} 通過，${failed} 失敗，共 ${passed + failed} 項`);
if (failed > 0) process.exit(1);
console.log('所有 smoke test 通過');
