# frontend/ — Obol demo frontend

Static, no-build frontend for the Arc Programmable Money Hackathon iteration.
It is deliberately kept
as plain HTML/CSS/JS so it can be opened from any static host and remain easy to
debug under deadline pressure.

## 文件（纯静态，无构建步骤）
- `index.html` — 5 个视图：Overview / Agent Console / Marketplace / Creators / x402
- `styles.css` — coin + ledger workbench visual system, responsive for demo recording
- `app.js` — all fetch logic, wired to `http://localhost:5001` by default

## 怎么跑（两个终端）
```bash
# 终端 1：后端
cd ../backend && pip install -r requirements.txt && python seed.py --force && python app.py

# 终端 2：前端（任意静态服务器都行）
cd .  &&  python -m http.server 5500
# 浏览器打开 http://localhost:5500
```
> API 地址可改：点页脚的 API 地址，或设 `localStorage.obol_api`（部署后指向线上后端）。

## 已实现页面
1. **Overview** — `GET /api/stats` 大数字（含 `decisions_made`、`usdc_saved_by_reuse`）
2. **Agent Console（重点）** — 输入问题+预算 → `POST /api/agent/run` → 渲染
   **plan + 决策表(buy/reuse/skip 三色徽章+理由+relevance+价格) + coverage 进度条 +
   confidence + 答案 + 收据(tx hash 跳动)**。这页就是 demo 视频主镜头。
3. **Marketplace** — `GET /api/articles`，文章卡片（价格 + locked 预览）
4. **Creators** — creator earnings plus a publish form backed by `POST /api/articles`
5. **x402** — demonstrates 402 Payment Required challenge and retry with `X-Payment`

## 验证
- Backend tests: `D:\python\python.exe -m pytest test_obol.py -q` from `backend/`
- Static JS syntax: `node --check frontend/app.js`
- Smoke path tested: reset → agent run → publish article → x402 402 challenge → x402 unlock

## Demo recording

Use the project positioning and evaluation boundaries in
`../PROGRAMMABLE_MONEY_SUBMISSION.md`. A new competition-specific demo script
will be added before final submission.
