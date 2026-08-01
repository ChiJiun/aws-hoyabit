# Implementation Plan: frontend-ui

## Overview

實作 `frontend/index.html` 的 `<script>` 區段內 6 個 JavaScript 函式。HTML 結構與 CSS 已完成，僅需將函式骨架（目前為註解）替換為完整實作。所有程式碼為 vanilla JavaScript，唯一外部依賴為 marked.js CDN。

## Tasks

- [x] 1. Implement coin selector and state management
  - [x] 1.1 Implement `initCoinSelector()` function
    - Replace the comment stub with full implementation
    - Bind click events to all `#coins .coin` buttons
    - Toggle `aria-pressed` attribute on click
    - Maintain `selectedCoins` array with FIFO eviction when exceeding 2
    - Ensure `aria-pressed` and `selectedCoins` are always in sync
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 8.1_

  - [ ]* 1.2 Write property tests for coin selector logic
    - **Property 1: Coin toggle consistency** — clicking toggles both aria-pressed and selectedCoins atomically
    - **Property 2: Maximum selection invariant** — selectedCoins.length never exceeds 2, FIFO eviction on third click
    - **Validates: Requirements 1.2, 1.3, 1.4**

- [x] 2. Implement loading state and error display
  - [x] 2.1 Implement `showLoading()` function
    - Hide `#input-panel`, `#result`, `#error`; show `#loading`
    - Disable submit button
    - Reset and start elapsed timer (`elapsedSeconds`, `elapsedInterval`) updating `#elapsed` in MM:SS format every second
    - Start message rotation (`messageInterval`) cycling through `LOADING_MESSAGES` every 10 seconds
    - Append timeout hint when `elapsedSeconds` reaches 600
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 10.1, 10.2_

  - [x] 2.2 Implement `showError(message)` function
    - Clear any running intervals (`elapsedInterval`, `messageInterval`)
    - Hide `#loading` and `#result`; show `#input-panel`
    - Set `#error.textContent` to the message and make it visible
    - Re-enable submit button
    - Preserve user's coin selections and question text (do not reset state)
    - _Requirements: 7.1, 7.2, 7.3, 10.1, 10.2, 10.3_

  - [ ]* 2.3 Write property tests for loading and error functions
    - **Property 6: Elapsed timer format** — for any non-negative integer n, display shows zero-padded MM:SS
    - **Property 9: Error message display** — showError(msg) sets #error.textContent to msg and makes it visible
    - **Property 10: View state mutual exclusivity** — exactly one view state active at any time
    - **Property 11: Error recovery preserves input** — error during loading preserves coin selections and question text
    - **Validates: Requirements 5.2, 7.1, 10.1, 10.2, 10.3**

- [x] 3. Checkpoint - Verify selector and state transitions
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement API communication and report rendering
  - [x] 4.1 Implement `callAnalysisApi(payload)` function
    - Send POST to `API_URL` with `Content-Type: application/json` and `JSON.stringify(payload)` body
    - No timeout/AbortController (Lambda may run 5-15 minutes)
    - On `!res.ok`: parse response JSON, throw Error with `body.error` or fallback message including status code
    - On network error: let the rejection propagate to caller
    - On success: return parsed JSON
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 11.1_

  - [x] 4.2 Implement `renderReport(data)` function
    - Clear both intervals (`elapsedInterval`, `messageInterval`)
    - Set `#report.innerHTML` to `marked.parse(data.report_text)`
    - Set `#dl-evidence.href` to `data.evidence_download_url`
    - Set `#dl-log.href` to `data.log_download_url`
    - Hide `#loading`; show `#result`
    - Re-enable submit button
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 10.1, 10.2_

  - [ ]* 4.3 Write property tests for API and report rendering
    - **Property 4: Contract C5 request format** — fetch uses POST, correct Content-Type, and body matches {"symbols": [...], "question": "trimmed"}
    - **Property 5: HTTP error field extraction** — 4xx/5xx with JSON error field calls showError with that value
    - **Property 7: Report rendering fidelity** — #report.innerHTML equals marked.parse(report_text)
    - **Property 8: Download link binding** — #dl-evidence.href and #dl-log.href match response URLs
    - **Validates: Requirements 4.1, 4.4, 6.1, 6.2, 6.3**

- [x] 5. Implement orchestrator and wire everything together
  - [x] 5.1 Implement `handleSubmit()` function
    - Clear previous error display
    - Validate: if `selectedCoins.length === 0`, call `showError` with coin selection message and return
    - Validate: if `question.trim()` is empty, call `showError` with question required message and return
    - Assemble payload: `{ symbols: [...selectedCoins], question: trimmedQuestion }`
    - Call `showLoading()`
    - Await `callAnalysisApi(payload)` in try/catch
    - On success: call `renderReport(data)`
    - On failure: call `showError(err.message)` with descriptive fallback
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 10.1, 10.2, 10.3_

  - [ ]* 5.2 Write property tests for handleSubmit validation
    - **Property 3: Invalid input rejection** — empty coins or whitespace-only question never triggers fetch, always calls showError
    - **Validates: Requirements 3.1, 3.2, 3.3**

- [x] 6. Final checkpoint - Full flow verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify complete flow: coin selection → submit → loading → report display
  - Verify error paths: validation errors, network errors, server errors all display correctly
  - Verify state transitions are mutually exclusive and timers are properly cleaned up

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All code is vanilla JavaScript within the existing `<script>` tag in `frontend/index.html`
- HTML structure and CSS are already complete — no UI modifications needed
- The only constant requiring deployment-time change is `API_URL`
- Property tests validate universal correctness properties from the design document
- For property tests, use a browser testing framework (e.g., Jest + jsdom) or manual verification

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "2.2"] },
    { "id": 2, "tasks": ["2.3", "4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3", "5.1"] },
    { "id": 4, "tasks": ["5.2"] }
  ]
}
```
