# Requirements Document

## Introduction

frontend-ui 模組負責 `frontend/index.html` 單檔前端，作為加密市場分析 AI Agent 的使用者介面。此介面為黑客松決賽 Live Demo 的主畫面，評審將透過此畫面觀察系統運作與產出。前端僅依賴 Handler HTTP 回應契約（C5），可透過 mock server 獨立開發與測試。

## Glossary

- **Frontend**: `frontend/index.html` 單檔應用程式，包含 HTML 結構、CSS 樣式與 vanilla JavaScript 邏輯
- **Coin_Selector**: 五個幣種按鈕（BTC/ETH/SOL/BNB/XRP）組成的選擇元件
- **Input_Panel**: 包含 Coin_Selector、題目 textarea 與送出按鈕的輸入區塊
- **Loading_View**: 分析執行中顯示的狀態畫面，含 spinner、輪播訊息與經過時間計時器
- **Report_View**: 分析完成後顯示報告內容與下載連結的結果區塊
- **Error_Display**: 顯示錯誤訊息的區塊
- **API_URL**: Lambda Function URL 常數，部署時替換
- **Contract_C5**: Handler HTTP 回應契約，定義請求格式 `POST {"symbols": [...], "question": "..."}` 與成功/失敗回應格式
- **Elapsed_Timer**: 以 `MM:SS` 格式顯示分析已經過的秒數
- **Status_Messages**: 預定義的輪播提示文字陣列，用於降低使用者等待焦慮

## Requirements

### Requirement 1: Coin Selection

**User Story:** As a user, I want to select one or two cryptocurrency symbols for analysis, so that the system knows which coins to analyze.

#### Acceptance Criteria

1. THE Coin_Selector SHALL render five buttons for BTC, ETH, SOL, BNB, and XRP with initial `aria-pressed="false"` state.
2. WHEN a user clicks an unselected coin button, THE Coin_Selector SHALL set that button's `aria-pressed` attribute to `"true"` and add the symbol to the selected list.
3. WHEN a user clicks a selected coin button, THE Coin_Selector SHALL set that button's `aria-pressed` attribute to `"false"` and remove the symbol from the selected list.
4. WHILE two coins are already selected, WHEN a user clicks a third unselected coin button, THE Coin_Selector SHALL deselect the earliest-selected coin and select the newly clicked coin, maintaining a maximum of two selected coins.
5. THE Coin_Selector SHALL support keyboard navigation, allowing users to activate buttons via Enter or Space key.

### Requirement 2: Question Input

**User Story:** As a user, I want to type my analysis question in a text field, so that the agent knows what to investigate.

#### Acceptance Criteria

1. THE Frontend SHALL provide a textarea element with a placeholder example demonstrating a valid analysis question.
2. THE Frontend SHALL allow the textarea to be resized vertically by the user.
3. WHEN the textarea receives focus, THE Frontend SHALL display a visible focus indicator using the accent color outline.

### Requirement 3: Input Validation

**User Story:** As a user, I want to receive clear feedback when my input is incomplete, so that I can correct it before submitting.

#### Acceptance Criteria

1. WHEN the user clicks the submit button with zero coins selected, THE Frontend SHALL call showError with a message indicating at least one coin must be selected.
2. WHEN the user clicks the submit button with an empty or whitespace-only question, THE Frontend SHALL call showError with a message indicating the question field is required.
3. THE Frontend SHALL not send an API request when validation fails.

### Requirement 4: API Communication

**User Story:** As a user, I want the frontend to send my analysis request to the backend, so that the AI agent can process it.

#### Acceptance Criteria

1. WHEN validation passes, THE Frontend SHALL send a POST request to API_URL with Content-Type `application/json` and body `{"symbols": [<selected coins>], "question": "<trimmed question text>"}` conforming to Contract_C5.
2. THE Frontend SHALL not set a fetch timeout, allowing the request to remain pending for up to 15 minutes to accommodate Lambda execution time.
3. IF the fetch request throws a network error, THEN THE Frontend SHALL display a descriptive error message suggesting the user verify the Function URL configuration and network connectivity.
4. IF the response status code is 4xx or 5xx, THEN THE Frontend SHALL parse the response JSON and display the `error` field value from the Contract_C5 error format.

### Requirement 5: Loading State

**User Story:** As a user, I want to see clear visual feedback during the analysis process, so that I know the system is working and approximately how long it has been running.

#### Acceptance Criteria

1. WHEN analysis begins, THE Loading_View SHALL hide the Input_Panel and any previous Report_View or Error_Display, and display the loading spinner.
2. THE Elapsed_Timer SHALL start at `00:00` and increment every second in `MM:SS` format.
3. THE Loading_View SHALL rotate through Status_Messages at an interval between 8 and 12 seconds, updating the displayed text to simulate progress.
4. WHILE the elapsed time exceeds 600 seconds (10 minutes) with no response received, THE Loading_View SHALL append a hint message indicating the execution is taking longer than expected, without aborting the request.
5. THE Frontend SHALL disable the submit button during the loading state to prevent duplicate submissions.

### Requirement 6: Report Rendering

**User Story:** As a user, I want to see the analysis report rendered as formatted HTML, so that I can easily read the results.

#### Acceptance Criteria

1. WHEN a successful response is received, THE Frontend SHALL parse `report_text` using `marked.parse()` and inject the resulting HTML into the `#report` container.
2. WHEN a successful response is received, THE Frontend SHALL set the `#dl-evidence` link href to the `evidence_download_url` value from the response.
3. WHEN a successful response is received, THE Frontend SHALL set the `#dl-log` link href to the `log_download_url` value from the response.
4. WHEN report rendering is complete, THE Frontend SHALL hide the Loading_View, show the Report_View, and re-enable the submit button.
5. THE Frontend SHALL clear the Elapsed_Timer interval and Status_Messages rotation interval after rendering completes.

### Requirement 7: Error Display

**User Story:** As a user, I want to see actionable error messages when something goes wrong, so that I can understand the issue and take corrective action.

#### Acceptance Criteria

1. WHEN showError is called, THE Error_Display SHALL show the provided message text in the `#error` element.
2. THE Error_Display SHALL present error messages that describe the problem and suggest a corrective action, avoiding generic messages like "發生錯誤".
3. WHEN showError is called during a loading state, THE Frontend SHALL hide the Loading_View, clear all running timers, and re-enable the submit button.

### Requirement 8: Accessibility

**User Story:** As a user with assistive technology, I want the interface to be accessible, so that I can use the application regardless of my input method or assistive needs.

#### Acceptance Criteria

1. THE Coin_Selector buttons SHALL use `aria-pressed` attribute to communicate toggle state to screen readers.
2. THE Frontend SHALL ensure all interactive elements are reachable and operable via keyboard Tab navigation.
3. THE Frontend SHALL respect the `prefers-reduced-motion` media query by disabling the spinner animation.
4. THE Frontend SHALL maintain a minimum color contrast ratio of 4.5:1 between text and background colors for WCAG AA compliance.

### Requirement 9: Live Demo Optimization

**User Story:** As a hackathon presenter, I want the interface to provide clear visual feedback at every stage, so that judges watching the screen recording can follow the system's operation.

#### Acceptance Criteria

1. THE Frontend SHALL use a single accent color (amber/gold `#e0a33e`) for all emphasis elements including selected coins, focus indicators, elapsed timer text, and code highlighting, creating visual consistency for screen recording.
2. THE Loading_View SHALL display the elapsed timer in monospace font, making time progression clearly readable on screen recordings.
3. WHEN a report is rendered, THE Frontend SHALL display download links for evidence and execution log, demonstrating traceability to judges.
4. THE Frontend SHALL render the complete interface within a 720px max-width centered layout, ensuring content remains readable on projected displays.

### Requirement 10: State Management

**User Story:** As a developer, I want clean state transitions between UI phases, so that the interface never shows conflicting or stale information.

#### Acceptance Criteria

1. THE Frontend SHALL maintain exactly three mutually exclusive view states: Input_Panel visible, Loading_View visible, or Report_View visible.
2. WHEN transitioning between states, THE Frontend SHALL hide all elements belonging to the previous state before showing elements of the new state.
3. IF an error occurs during loading, THEN THE Frontend SHALL transition back to the Input_Panel state with the Error_Display visible, preserving the user's previous coin selections and question text.

### Requirement 11: Deployment Independence

**User Story:** As a developer, I want the frontend to be fully decoupled from backend internals, so that it can be developed and tested independently.

#### Acceptance Criteria

1. THE Frontend SHALL depend only on Contract_C5 request and response formats, with no knowledge of backend internal structure.
2. THE Frontend SHALL define API_URL as a single top-level constant, enabling deployment-time replacement without modifying logic code.
3. THE Frontend SHALL function as a static file servable from any HTTP server or S3 static website hosting without build steps or server-side processing.
