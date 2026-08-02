/**
 * structure_check.mjs — index.html 結構完整性檢查
 *
 * 確認關鍵元素存在且不重複（重複 id 會讓 getElementById 取到錯的元素），
 * 並驗證內嵌 script 可被正確取出與解析。
 *
 * 執行：node frontend/tests/structure_check.mjs
 */

import { readFileSync, writeFileSync, unlinkSync } from 'fs';
import { resolve, dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(__dirname, '..');
const html = readFileSync(join(FRONTEND, 'index.html'), 'utf8');

let fail = 0;
const check = (cond, msg) => {
  console.log(`${cond ? 'ok  ' : 'FAIL'} ${msg}`);
  if (!cond) fail++;
};
const count = needle => html.split(needle).length - 1;

console.log('--- 必要元素唯一性（重複 id 會讓 JS 取到錯誤元素）---');
const uniqueIds = [
  'view-input', 'view-result', 'topbar', 'topnav', 'loading', 'loading-msg',
  'elapsed', 'error', 'coins-group', 'question', 'presets', 'btn-go',
  'btn-restart', 'load-steps', 'dl-report', 'dl-ev', 'dl-log',
  'hdr-qtype', 'hdr-run', 'hdr-elapsed'
];
for (const id of uniqueIds) {
  check(count(`id="${id}"`) === 1, `#${id} 恰好出現一次（實際 ${count(`id="${id}"`)}）`);
}

console.log('\n--- 標題層級 ---');
check(count('<h1') === 1, `恰有一個 h1（實際 ${count('<h1')}）`);

console.log('\n--- 品牌與版面 ---');
check(count('class="brandbar"') === 1, '品牌列存在');
check(count('logo-mark') >= 2, 'logo 圖標存在（含可替換的 img 與內建 svg）');
check(count('id="logo-img"') === 1 && count('id="logo-fallback"') === 1,
  'logo 具備官方素材與內建替代兩種來源');
check(count('id="mascot-img"') === 1 && count('id="mascot-fallback"') === 1,
  '吉祥物具備官方素材與內建替代兩種來源');
check(html.includes("assets/logo.svg"), '會嘗試載入 assets/logo.svg');
check(html.includes("assets/mascot"), '會嘗試載入 assets/mascot');
check(html.includes('<b>H</b>OYA BIT'), 'logo 字標為 HOYA BIT，H 以品牌色強調');
check(html.includes('#f26722'), 'logo 使用品牌橘 #f26722');
check(html.includes('aria-label="HOYA BIT 標誌"'), 'logo 有無障礙標籤');
check(count('class="hero"') === 1, 'hero 版面存在');
check(/\.hero\{[^}]*grid-template-columns/.test(html), 'hero 使用兩欄格線');
check(/\.intro\{min-height:100vh/.test(html), '首頁佔滿視窗高度');
check(count('class="deliver"') === 1, '底部交付物列存在');
check(html.includes('BUILT WITH AWS KIRO'), '標示採用 AWS Kiro（加分項）');

console.log('\n--- 幣種與題型 ---');
check(count('class="coin"') === 5, `五個幣種按鈕（實際 ${count('class="coin"')}）`);
['BTC', 'ETH', 'SOL', 'BNB', 'XRP'].forEach(s =>
  check(html.includes(`>${s}</button>`), `幣種按鈕 ${s} 存在`));

console.log('\n--- 定位聲明 ---');
check(/不提供投資建議/.test(html), '首頁聲明不提供投資建議');

console.log('\n--- 內嵌 script ---');
const m = html.match(/<script>\s*\r?\n([\s\S]*?)<\/script>/);
check(!!m, '可取出內嵌 script');
if (m) {
  const tmp = join(FRONTEND, '_syntax_tmp.js');
  writeFileSync(tmp, m[1]);
  let ok = true;
  try {
    execSync(`node --check "${tmp}"`, { stdio: 'pipe' });
  } catch (e) {
    ok = false;
    console.error(String(e.stderr || e.message).slice(0, 400));
  } finally {
    try { unlinkSync(tmp); } catch (e) { /* 已刪除 */ }
  }
  check(ok, 'script 語法正確');
  check(!/\bsrc=["']app\.js/.test(html), '維持單檔架構，未外連 app.js');
}

console.log(`\n${'='.repeat(48)}`);
if (fail) { console.log(`${fail} 項未通過`); process.exit(1); }
console.log('結構檢查通過');
