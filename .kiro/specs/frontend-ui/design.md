# Design Document: frontend-ui

## Overview

`frontend/index.html` 為加密市場分析 AI Agent 的單檔前端。HTML 結構與 CSS 已完成，本設計僅涵蓋 `<script>` 標籤內的 JavaScript 實作。前端唯一外部依賴為 Contract C5（Handler HTTP 回應格式）與 marked.js CDN。

## Architecture

```
┌─────────────────────────────────────────────────┐
│  frontend/index.html                            │
│                                                 │
│  ┌───────────────┐  ┌────────────────────────┐  │
│  │  Constants    │  │  State                 │  │
│  │  - API_URL    │  │  - selectedCoins[]     │  │
│  │  - LOADING_   │  │  - elapsedInterval     │  │
│  │    MESSAGES   │  │  - messageInterval     │  │
│  └───────────────┘  │  - elapsedSeconds      │  │
│                     └────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │  Functions                               │   │
│  │                                          │   │
│  │  initCoinSelector()  ──► DOM binding     │   │
│  │  handleSubmit()      ──► orchestrator    │   │
│  │  callAnalysisApi()   ──► fetch(C5)       │   │
│  │  showLoading()       ──► state transition│   │
│  │  renderReport()      ──► state transition│   │
│  │  showError()         ──► state transition│   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  External: marked.js CDN (Markdown → HTML)      │
└─────────────────────────────────────────────────┘
         │
         │  POST (Contract C5)
         ▼
┌─────────────────────┐
│  Lambda Function URL│
└─────────────────────┘
```

## Components

### 1. Constants

```javascript
const API_URL = "https://...lambda-url.us-east-1.on.aws/";

const LOADING_MESSAGES = [
  "正在規劃資料蒐集範圍",
  "正在讀取價格與技術指標",
  "正在檢索新聞與官方公告",
  "正在查詢鏈上活躍度",
  "正在整理證據並產出報告"
];
```

`API_URL` 為唯一需要部署時替換的常數，其餘皆為展示用 UI 文案。

### 2. Module-Level State

```javascript
let selectedCoins = [];       // 目前選取的幣種，最多 2 個
let elapsedInterval = null;   // setInterval ID — 每秒更新計時器
let messageInterval = null;   // setInterval ID — 輪播提示訊息
let elapsedSeconds = 0;       // 已經過秒數
let messageIndex = 0;         // 目前顯示的提示訊息 index
```

所有 interval ID 集中管理，確保任何狀態轉換都能正確清除 timer。

### 3. View States (Mutually Exclusive)

前端維持三個互斥的畫面狀態：

| State | Visible Elements | Hidden Elements |
|-------|-----------------|-----------------|
| INPUT | `#input-panel` | `#loading`, `#result` |
| LOADING | `#loading` | `#input-panel`, `#result` |
| RESULT | `#result` | `#input-panel`, `#loading` |

`#error` 為附加元素，僅在 INPUT 狀態時可見（錯誤發生時顯示）。任何狀態轉換函式必須先隱藏所有非目標元素再顯示目標元素。

## Interfaces

### initCoinSelector()

```javascript
function initCoinSelector() {
  const buttons = document.querySelectorAll('#coins .coin');
  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      const symbol = btn.textContent.trim();
      if (btn.getAttribute('aria-pressed') === 'true') {
        // 取消選取
        btn.setAttribute('aria-pressed', 'false');
        selectedCoins = selectedCoins.filter(s => s !== symbol);
      } else {
        // 選取（超過 2 個時淘汰最早的）
        if (selectedCoins.length >= 2) {
          const evicted = selectedCoins.shift();
          const evictedBtn = [...buttons].find(b => b.textContent.trim() === evicted);
          if (evictedBtn) evictedBtn.setAttribute('aria-pressed', 'false');
        }
        selectedCoins.push(symbol);
        btn.setAttribute('aria-pressed', 'true');
      }
    });
  });
}
```

- FIFO 淘汰策略：`selectedCoins` 當作 queue，shift() 移除最早加入的
- aria-pressed 與 selectedCoins 始終同步

### handleSubmit()

```javascript
async function handleSubmit() {
  // 1. 清除先前的錯誤顯示
  document.getElementById('error').style.display = 'none';

  // 2. 驗證
  if (selectedCoins.length === 0) {
    return showError('請至少選擇一個幣種進行分析。');
  }
  const question = document.getElementById('question').value.trim();
  if (!question) {
    return showError('請輸入分析題目，讓 Agent 知道要調查什麼。');
  }

  // 3. 組裝 payload (Contract C5)
  const payload = { symbols: [...selectedCoins], question };

  // 4. 切換到 Loading 狀態
  showLoading();

  try {
    const data = await callAnalysisApi(payload);
    renderReport(data);
  } catch (err) {
    showError(err.message || '無法連線到分析服務，請確認 Function URL 是否正確，以及網路連線是否正常。');
  }
}
```

### callAnalysisApi(payload)

```javascript
async function callAnalysisApi(payload) {
  const res = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `伺服器回傳錯誤 (${res.status})，請稍後再試。`);
  }

  return await res.json();
}
```

- 不設 AbortController / timeout：Lambda 分析可能執行 5-15 分鐘
- 4xx/5xx：解析 response JSON 取 `error` 欄位（Contract C5 錯誤格式）
- 網路錯誤（fetch reject）：由外層 catch 處理

### showLoading()

```javascript
function showLoading() {
  // 隱藏其他狀態
  document.getElementById('input-panel').style.display = 'none';
  document.getElementById('result').style.display = 'none';
  document.getElementById('error').style.display = 'none';

  // 顯示 loading
  document.getElementById('loading').style.display = 'block';

  // 停用送出按鈕
  document.getElementById('submit').disabled = true;

  // 啟動計時器
  elapsedSeconds = 0;
  messageIndex = 0;
  document.getElementById('elapsed').textContent = '00:00';
  document.getElementById('loading-msg').textContent = LOADING_MESSAGES[0];

  elapsedInterval = setInterval(() => {
    elapsedSeconds++;
    const mm = String(Math.floor(elapsedSeconds / 60)).padStart(2, '0');
    const ss = String(elapsedSeconds % 60).padStart(2, '0');
    document.getElementById('elapsed').textContent = `${mm}:${ss}`;

    // 超過 10 分鐘提示
    if (elapsedSeconds === 600) {
      document.getElementById('loading-msg').textContent +=
        '\n（執行時間較長，請耐心等候）';
    }
  }, 1000);

  messageInterval = setInterval(() => {
    messageIndex = (messageIndex + 1) % LOADING_MESSAGES.length;
    document.getElementById('loading-msg').textContent = LOADING_MESSAGES[messageIndex];
  }, 10000); // 10 秒輪播一次
}
```

### renderReport(data)

```javascript
function renderReport(data) {
  // 清除 timers
  clearInterval(elapsedInterval);
  clearInterval(messageInterval);
  elapsedInterval = null;
  messageInterval = null;

  // 渲染報告
  document.getElementById('report').innerHTML = marked.parse(data.report_text);

  // 設定下載連結
  document.getElementById('dl-evidence').href = data.evidence_download_url;
  document.getElementById('dl-log').href = data.log_download_url;

  // 切換到 Result 狀態
  document.getElementById('loading').style.display = 'none';
  document.getElementById('result').style.display = 'block';

  // 恢復送出按鈕
  document.getElementById('submit').disabled = false;
}
```

### showError(message)

```javascript
function showError(message) {
  // 如果正在 loading，先清除
  if (elapsedInterval || messageInterval) {
    clearInterval(elapsedInterval);
    clearInterval(messageInterval);
    elapsedInterval = null;
    messageInterval = null;
  }

  // 切換回 Input 狀態（保留使用者的選取與文字）
  document.getElementById('loading').style.display = 'none';
  document.getElementById('result').style.display = 'none';
  document.getElementById('input-panel').style.display = 'block';

  // 顯示錯誤
  const el = document.getElementById('error');
  el.textContent = message;
  el.style.display = 'block';

  // 恢復送出按鈕
  document.getElementById('submit').disabled = false;
}
```

## Data Flow

```
User Input ──► handleSubmit()
                 │
                 ├─ validation fails ──► showError(msg)
                 │
                 ├─ validation passes
                 │     │
                 │     ├─ showLoading()
                 │     │
                 │     ├─ callAnalysisApi(payload)
                 │     │     │
                 │     │     ├─ fetch rejects ──► throw Error
                 │     │     ├─ res.ok === false ──► throw Error(body.error)
                 │     │     └─ res.ok === true ──► return JSON
                 │     │
                 │     ├─ success ──► renderReport(data)
                 │     └─ failure ──► showError(err.message)
                 │
                 └─ (submit button re-enabled in both paths)
```

## Contract C5 Integration

### Request (sent by Frontend)

```json
{
  "symbols": ["BTC"] | ["BTC", "ETH"],
  "question": "非空字串，已 trim"
}
```

### Successful Response (200)

```json
{
  "run_id": "run_20260801_042151",
  "report_text": "# 市場判斷\n...",
  "evidence_download_url": "https://s3...presigned",
  "log_download_url": "https://s3...presigned"
}
```

### Error Response (4xx/5xx)

```json
{
  "error": "明確錯誤說明"
}
```

## Error Handling Strategy

| Error Source | Detection | User Message |
|---|---|---|
| No coins selected | `selectedCoins.length === 0` | 「請至少選擇一個幣種進行分析。」 |
| Empty question | `question.trim() === ''` | 「請輸入分析題目，讓 Agent 知道要調查什麼。」 |
| Network error | fetch throws | 「無法連線到分析服務，請確認 Function URL 是否正確，以及網路連線是否正常。」 |
| Server error | `!res.ok` | 顯示 `response.error` 欄位，fallback 為 `伺服器回傳錯誤 (status)` |

## Accessibility

- `aria-pressed` 屬性隨選取狀態同步更新
- 所有按鈕為原生 `<button>`，天生支援 keyboard focus/activation
- `prefers-reduced-motion: reduce` → spinner animation 停止（CSS 已處理）
- 色彩對比：深墨藍 (#0f1720) 上的淺灰文字 (#e6ecf2) 對比度 > 12:1

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Coin toggle consistency

*For any* coin button, clicking it SHALL toggle both its `aria-pressed` attribute and the `selectedCoins` array membership atomically — if the button was unselected, it becomes selected and the symbol is added; if it was selected, it becomes unselected and the symbol is removed.

**Validates: Requirements 1.2, 1.3**

### Property 2: Maximum selection invariant

*For any* sequence of coin button clicks, the length of `selectedCoins` SHALL never exceed 2. When a third coin is clicked while two are already selected, the earliest-selected coin is evicted (FIFO) and the new coin takes its place.

**Validates: Requirements 1.4**

### Property 3: Invalid input rejection

*For any* input state where `selectedCoins` is empty OR the question textarea contains only whitespace characters, calling `handleSubmit()` SHALL not invoke `fetch()` and SHALL call `showError()` with a descriptive message.

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 4: Contract C5 request format

*For any* valid input (1-2 selected coins and a non-whitespace question string), the `fetch()` call SHALL use method POST, Content-Type `application/json`, and a body equal to `{"symbols": [selected coins in order], "question": "trimmed question text"}`.

**Validates: Requirements 4.1**

### Property 5: HTTP error field extraction

*For any* HTTP response with status code in the 400-599 range that contains a JSON body with an `error` field, `showError()` SHALL be called with that `error` field value as the message.

**Validates: Requirements 4.4**

### Property 6: Elapsed timer format

*For any* non-negative integer number of elapsed seconds `n`, the timer display SHALL show the string `MM:SS` where `MM = floor(n/60)` zero-padded to 2 digits and `SS = n % 60` zero-padded to 2 digits.

**Validates: Requirements 5.2**

### Property 7: Report rendering fidelity

*For any* string `report_text` in a successful response, the `#report` element's innerHTML SHALL equal `marked.parse(report_text)`.

**Validates: Requirements 6.1**

### Property 8: Download link binding

*For any* successful response containing `evidence_download_url` and `log_download_url` fields, `#dl-evidence.href` SHALL equal `evidence_download_url` and `#dl-log.href` SHALL equal `log_download_url`.

**Validates: Requirements 6.2, 6.3**

### Property 9: Error message display

*For any* non-empty string `msg`, calling `showError(msg)` SHALL set `#error.textContent` to `msg` and set `#error.style.display` to a visible value.

**Validates: Requirements 7.1**

### Property 10: View state mutual exclusivity

*For any* point in time after initialization, exactly one of the three view states (INPUT, LOADING, RESULT) SHALL be active. After any state transition function (`showLoading`, `renderReport`, `showError`), elements belonging to non-active states SHALL have `display: none`.

**Validates: Requirements 10.1, 10.2**

### Property 11: Error recovery preserves input

*For any* combination of selected coins and question text, if an error occurs during the LOADING state, the transition back to INPUT state SHALL preserve the user's previous coin selections (both `selectedCoins` array and button `aria-pressed` attributes) and the question textarea value unchanged.

**Validates: Requirements 10.3**
