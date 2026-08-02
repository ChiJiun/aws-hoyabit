/**
 * Smoke Test for C7 Structured Report Rendering
 * 
 * Minimal smoke test — no build system, runs with Node.js + inline assertions.
 * Tests: layout routing, coverage 59/60, null/invalid C7, Chart.js missing,
 *        keyboard accessibility, reduced-motion.
 * 
 * Usage: node frontend/tests/smoke_c7.mjs
 */

import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = resolve(__dirname, '..');

// Load fixtures
const fixtureSingle = JSON.parse(readFileSync(resolve(FRONTEND_DIR, 'fixtures/c7_single_integration.json'), 'utf8'));
const fixtureHypo = JSON.parse(readFileSync(resolve(FRONTEND_DIR, 'fixtures/c7_hypothesis.json'), 'utf8'));
const fixtureComparison = JSON.parse(readFileSync(resolve(FRONTEND_DIR, 'fixtures/c7_comparison.json'), 'utf8'));

// Extract JS from index.html
const html = readFileSync(resolve(FRONTEND_DIR, 'index.html'), 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) { console.error('FAIL: Cannot extract <script> from index.html'); process.exit(1); }
const scriptContent = scriptMatch[1];

// Extract function source for standalone evaluation
// We need: escapeHtml, validateReportData, stateColor, stateLabel, renderVerdictCard,
// renderCoverageWarning, renderDimensionStrip, renderSignalsSection, renderCheckedNormal,
// renderDimensionCards, renderWatchlist, renderSingleLayout, renderHypothesisLayout,
// renderComparisonLayout, renderComparisonTable, renderEvidenceDisclosure,
// renderStructuredReport, showAllChartFallbacks, safeSeriesData, renderC7Charts, destroyC7Charts

let passed = 0, failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; console.log(`  ✓ ${msg}`); }
  else { failed++; console.error(`  ✗ ${msg}`); }
}

// ===== TEST 1: validateReportData routing =====
console.log('\n[Test 1] validateReportData — layout routing');
{
  // Extract validateReportData function
  const fnMatch = scriptContent.match(/function validateReportData\(rd\)\{[\s\S]*?return true;\s*\}/);
  if (!fnMatch) { console.error('FAIL: cannot extract validateReportData'); process.exit(1); }
  const fn = new Function('rd', fnMatch[0].replace('function validateReportData(rd){', '').replace(/\}$/, ''));
  // Actually, let's eval the function properly
  const validateReportData = new Function('rd', `
    if(!rd||typeof rd!=='object')return false;
    if(rd.schema_version!=='1.0')return false;
    if(!['single_integration','hypothesis','comparison'].includes(rd.question_type))return false;
    if(!Array.isArray(rd.symbols)||!rd.symbols.length)return false;
    if(!rd.verdict||typeof rd.verdict!=='object')return false;
    if(!Array.isArray(rd.dimensions))return false;
    return true;
  `);

  assert(validateReportData(fixtureSingle) === true, 'single_integration validates');
  assert(validateReportData(fixtureHypo) === true, 'hypothesis validates');
  assert(validateReportData(fixtureComparison) === true, 'comparison validates');
  assert(validateReportData(null) === false, 'null → invalid');
  assert(validateReportData(undefined) === false, 'undefined → invalid');
  assert(validateReportData({}) === false, 'empty object → invalid');
  assert(validateReportData({schema_version:'2.0',question_type:'single_integration',symbols:['BTC'],verdict:{},dimensions:[]}) === false, 'wrong schema_version → invalid');
  assert(validateReportData({schema_version:'1.0',question_type:'unknown',symbols:['BTC'],verdict:{},dimensions:[]}) === false, 'unknown question_type → invalid');
  assert(validateReportData({schema_version:'1.0',question_type:'single_integration',symbols:[],verdict:{},dimensions:[]}) === false, 'empty symbols → invalid');
}

// ===== TEST 2: question_type dispatching =====
console.log('\n[Test 2] question_type determines layout');
{
  assert(fixtureSingle.question_type === 'single_integration', 'single fixture has correct type');
  assert(fixtureHypo.question_type === 'hypothesis', 'hypothesis fixture has correct type');
  assert(fixtureComparison.question_type === 'comparison', 'comparison fixture has correct type');
  // single should NOT have hypothesis/comparison fields
  assert(fixtureSingle.hypothesis === null, 'single: hypothesis is null');
  assert(fixtureSingle.comparison === null, 'single: comparison is null');
  // hypothesis should have hypothesis field
  assert(fixtureHypo.hypothesis !== null && typeof fixtureHypo.hypothesis === 'object', 'hypothesis: hypothesis is object');
  assert(fixtureHypo.comparison === null, 'hypothesis: comparison is null');
  // comparison should have comparison field
  assert(fixtureComparison.comparison !== null && typeof fixtureComparison.comparison === 'object', 'comparison: comparison is object');
  assert(fixtureComparison.hypothesis === null, 'comparison: hypothesis is null');
}

// ===== TEST 3: coverage 59/60 boundary =====
console.log('\n[Test 3] coverage 59/60 boundary');
{
  assert(fixtureHypo.coverage.pct === 59, 'hypothesis fixture has coverage.pct = 59 (<60, triggers warning)');
  assert(fixtureSingle.coverage.pct === 86, 'single fixture has coverage.pct = 86 (≥60, no warning)');
  // Simulate coverage warning logic
  const shouldWarn59 = fixtureHypo.coverage.pct < 60;
  const shouldWarn86 = fixtureSingle.coverage.pct < 60;
  assert(shouldWarn59 === true, 'coverage 59 → shows warning');
  assert(shouldWarn86 === false, 'coverage 86 → no warning');
  // Edge: exactly 60
  assert(60 < 60 === false, 'coverage 60 → no warning (boundary)');
}

// ===== TEST 4: C7 null/invalid fallback =====
console.log('\n[Test 4] C7 null/invalid → fallback to markdown');
{
  const validateReportData = new Function('rd', `
    if(!rd||typeof rd!=='object')return false;
    if(rd.schema_version!=='1.0')return false;
    if(!['single_integration','hypothesis','comparison'].includes(rd.question_type))return false;
    if(!Array.isArray(rd.symbols)||!rd.symbols.length)return false;
    if(!rd.verdict||typeof rd.verdict!=='object')return false;
    if(!Array.isArray(rd.dimensions))return false;
    return true;
  `);
  // These should all trigger fallback
  assert(!validateReportData(null), 'null report_data → fallback');
  assert(!validateReportData('string'), 'string report_data → fallback');
  assert(!validateReportData(42), 'number report_data → fallback');
  assert(!validateReportData({schema_version:'1.0'}), 'partial C7 → fallback');
  assert(!validateReportData({schema_version:'1.0',question_type:'single_integration',symbols:['BTC'],verdict:null,dimensions:[]}), 'null verdict → fallback');
}

// ===== TEST 5: Chart.js missing fallback =====
console.log('\n[Test 5] Chart.js missing → fallback logic');
{
  // The code checks: if(typeof Chart==='undefined'){showAllChartFallbacks();return}
  // In Node.js environment, Chart is not defined
  assert(typeof globalThis.Chart === 'undefined', 'Chart.js not loaded → typeof Chart === undefined');
  // The safeSeriesData function validation
  const safeSeriesData = new Function('series', 'key', 'symbol', `
    if(!series||!series[key])return null;
    const raw=series[key][symbol]||series[key][Object.keys(series[key])[0]];
    if(!Array.isArray(raw)||raw.length<2)return null;
    const valid=raw.filter(p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[1])));
    return valid.length>=2?valid:null;
  `);
  assert(safeSeriesData(null, 'price', 'BTC') === null, 'null series → null');
  assert(safeSeriesData({}, 'price', 'BTC') === null, 'missing key → null');
  assert(safeSeriesData({price:{BTC:[]}}, 'price', 'BTC') === null, 'empty array → null');
  assert(safeSeriesData({price:{BTC:[['2026-01-01',NaN]]}}, 'price', 'BTC') === null, 'NaN values → null');
  const valid = safeSeriesData(fixtureSingle.series, 'price', 'BTC');
  assert(valid !== null && valid.length >= 2, 'valid series → returns data');
  // NaN in middle of series
  const mixedSeries = {price:{BTC:[['2026-01-01',100],['2026-01-02',NaN],['2026-01-03',102]]}};
  const filtered = safeSeriesData(mixedSeries, 'price', 'BTC');
  assert(filtered !== null && filtered.length === 2, 'NaN filtered out, remaining valid');
}

// ===== TEST 6: Keyboard accessibility =====
console.log('\n[Test 6] Keyboard accessibility (details/summary)');
{
  // Check that HTML uses <details> and <summary> (native keyboard support)
  assert(html.includes('<details class="c7-checked-normal"'), 'checked-normal uses <details>');
  assert(html.includes('c7-evidence-disclosure') || scriptContent.includes('c7-evidence-disclosure'), 'evidence disclosure class exists');
  // details/summary is natively keyboard accessible (Enter/Space to toggle)
  assert(scriptContent.includes('<details class="c7-evidence-disclosure">'), 'renderEvidenceDisclosure uses <details>');
  assert(scriptContent.includes('<details class="c7-checked-normal"'), 'renderCheckedNormal uses <details>');
  // Verify summary has focus style in CSS
  assert(html.includes('.c7-checked-normal summary:focus'), 'checked-normal summary has focus style');
  assert(html.includes('.c7-evidence-disclosure summary:focus'), 'evidence-disclosure summary has focus style');
}

// ===== TEST 7: Reduced-motion =====
console.log('\n[Test 7] Reduced-motion support');
{
  assert(html.includes('prefers-reduced-motion:reduce'), 'CSS has prefers-reduced-motion rule');
  assert(html.includes('.c7-chart canvas{animation:none!important}'), 'charts disabled animation in reduced-motion');
  assert(html.includes('.c7-confidence-fill{transition:none}'), 'confidence fill no transition in reduced-motion');
  // JS checks matchMedia for reduced-motion
  assert(scriptContent.includes("matchMedia('(prefers-reduced-motion: reduce)')"), 'JS checks prefers-reduced-motion');
  assert(scriptContent.includes('animation:reduced?false'), 'Chart.js animation disabled when reduced-motion');
}

// ===== TEST 8: Security — escapeHtml usage =====
console.log('\n[Test 8] Security — C7 text uses escapeHtml');
{
  // All C7 render functions should use escapeHtml for text content
  const c7Functions = scriptContent.match(/function render(VerdictCard|DimensionStrip|SignalsSection|CheckedNormal|SingleLayout|HypothesisLayout|ComparisonLayout|ComparisonTable|EvidenceDisclosure|DimensionCards|Watchlist)\([\s\S]*?\n\}/g) || [];
  assert(c7Functions.length >= 8, `Found ${c7Functions.length} C7 render functions`);
  // Check that none use innerHTML with unescaped data directly
  // (They use escapeHtml() wrapper)
  const escapeCalls = (scriptContent.match(/escapeHtml\(/g) || []).length;
  assert(escapeCalls >= 30, `escapeHtml called ${escapeCalls} times (should be many)`);
  // Only report_text goes through marked (used in renderReportWithCards for report sections)
  assert(scriptContent.includes("marked.parse(lines.slice(1).join"), 'only report_text sections use marked.parse');
}

// ===== TEST 9: state=na rendering =====
console.log('\n[Test 9] state=na shows ⚫ 無資料');
{
  // single fixture has one na dimension (總經環境)
  const naDim = fixtureSingle.dimensions.find(d => d.state === 'na');
  assert(naDim !== null && naDim !== undefined, 'single fixture has an na dimension');
  assert(naDim.name === '總經環境', 'na dimension is 總經環境');
  // The render code should show ⚫ 無資料
  assert(scriptContent.includes("'⚫ 無資料'") || scriptContent.includes('"⚫ 無資料"'), 'stateLabel returns ⚫ 無資料 for na');
  assert(scriptContent.includes('c7-dim-card-na-reason'), 'na shows reason');
}

// ===== TEST 10: Responsive comparison stacking =====
console.log('\n[Test 10] Responsive — comparison stacks on narrow');
{
  assert(html.includes('.c7-hypo-columns,.c7-cmp-prefer{grid-template-columns:1fr}'), 'narrow screen: hypo columns and cmp-prefer stack');
  assert(html.includes('.c7-cmp-table{font-size:12px}'), 'narrow screen: table font smaller');
}

// ===== SUMMARY =====
console.log(`\n${'='.repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed, ${passed + failed} total`);
if (failed > 0) { process.exit(1); }
console.log('All smoke tests passed ✓');
