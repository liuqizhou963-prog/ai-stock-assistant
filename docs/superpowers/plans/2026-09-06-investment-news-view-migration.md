# 资讯看板替换与股票助手入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution) or superpowers:subagent-driven-development (task-by-task execution) to implement this plan.

**Goal:** 将 `investment-news-assistant` 的资讯页面及其后端实现直接复制为当前项目的资讯端，同时保持当前项目股票助手端所有文件和逻辑不变。

**Architecture:** 当前 React 应用只负责在根入口选择资讯视图或现有 `AgentWorkspace`。资讯视图通过 iframe 加载复制后的资讯服务（端口 8888），资讯服务继续使用复制来的 HTML、JavaScript、数据文件和 FastAPI 后端；复制后的资讯入口按钮通过顶层导航进入当前项目 `?view=agent`，股票助手返回时回到资讯视图。旧资讯 API 仅在股票助手验证通过后移除。

**Tech Stack:** React 19 + TypeScript + Vite；原资讯项目原生 HTML/JavaScript + FastAPI；Windows PowerShell；Git。

---

### Task 1: 建立资讯项目副本并保留原始文件结构

**Files:**
- Create: `apps/news-service/`（从 `C:\Users\11982\Desktop\搭建\investment-news-assistant` 复制）
- Preserve: `apps/news-service/index.html`
- Preserve: `apps/news-service/galaxy-background.js`
- Preserve: `apps/news-service/data.js`
- Preserve: `apps/news-service/sources.json`
- Preserve: `apps/news-service/server.py`
- Preserve: `apps/news-service/assistant/`, `apps/news-service/docs/`, `apps/news-service/mcp_router/`, `apps/news-service/schema_retrieval/`, `apps/news-service/scripts/`, `apps/news-service/tests/`

- [ ] **Step 1: Confirm source files and target do not overlap**

Run:

```powershell
Test-Path 'C:\Users\11982\Desktop\搭建\investment-news-assistant\index.html'
Test-Path 'D:\新搭建\apps\news-service'
```

Expected: first command returns `True`; second returns `False` or an empty target that contains no user changes.

- [ ] **Step 2: Copy the source project without its Git metadata or runtime caches**

Run:

```powershell
New-Item -ItemType Directory -Force 'D:\新搭建\apps\news-service' | Out-Null
Get-ChildItem -Force 'C:\Users\11982\Desktop\搭建\investment-news-assistant' |
  Where-Object { $_.Name -notin @('.git', '__pycache__', '.pytest_cache') } |
  Copy-Item -Destination 'D:\新搭建\apps\news-service' -Recurse -Force
```

Expected: `apps/news-service/index.html` and `apps/news-service/server.py` exist, and no `.git` directory is created inside the copy.

- [ ] **Step 3: Verify the copy before modifying it**

Run:

```powershell
Get-FileHash 'C:\Users\11982\Desktop\搭建\investment-news-assistant\index.html'
Get-FileHash 'D:\新搭建\apps\news-service\index.html'
Get-FileHash 'C:\Users\11982\Desktop\搭建\investment-news-assistant\server.py'
Get-FileHash 'D:\新搭建\apps\news-service\server.py'
```

Expected: each source hash equals its copied-file hash.

- [ ] **Step 4: Commit the untouched copied baseline**

```powershell
git add -- apps/news-service
git commit -m "feat: copy investment news service"
```

### Task 2: Change only the copied资讯入口

**Files:**
- Modify: `apps/news-service/index.html`
- Test: `apps/news-service/tests/test_stock_assistant_entry.py`
- Do not modify: `apps/renderer/src/App.tsx` agent component body or any file under `apps/backend/app/agent/`

- [ ] **Step 1: Write a failing contract test for the new entry behavior**

Create `apps/news-service/tests/test_stock_assistant_entry.py`:

```python
from pathlib import Path


INDEX_HTML = Path(__file__).resolve().parents[1] / "index.html"


def test_news_page_routes_to_current_stock_assistant():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="viewStockAssistant"' in html
    assert '<span class="nm">股票助手</span>' in html
    assert 'id="viewWorkbench"' not in html
    assert '<span class="nm">行情工作台</span>' not in html
    assert "window.top.location.href" in html
    assert "document.getElementById('assistantToggle').onclick = openStockAssistant" in html
    assert 'id="assistant"' not in html
    assert "toggleAssistant" not in html
```

- [ ] **Step 2: Run the contract test and confirm it fails**

Run:

```powershell
python -m pytest tests/test_stock_assistant_entry.py -q
```

Working directory: `D:\新搭建\apps\news-service`.

Expected: FAIL because the copied page still contains `viewWorkbench` and the original assistant drawer.

- [ ] **Step 3: Replace the copied page's workbench navigation item**

Change the copied page navigation element from:

```html
<div class="nav-item" id="viewWorkbench" data-view="workbench" role="button" tabindex="0" aria-label="切换到行情工作台">
  <span class="dot" style="background:#38bdf8"></span><span class="nm">行情工作台</span>
</div>
```

to:

```html
<div class="nav-item" id="viewStockAssistant" role="button" tabindex="0" aria-label="进入股票助手">
  <span class="dot" style="background:#38bdf8"></span><span class="nm">股票助手</span>
</div>
```

- [ ] **Step 4: Make both copied-page entry buttons navigate the parent tab**

Add this helper near the copied page's inline script start:

```js
function openStockAssistant() {
  var parentOrigin = 'http://127.0.0.1:5174';
  try {
    if (document.referrer) parentOrigin = new URL(document.referrer).origin;
  } catch (error) {}
  window.top.location.href = parentOrigin + '/?view=agent';
}
```

Bind it after the copied page's DOM references are initialized:

```js
document.getElementById('viewStockAssistant').onclick = openStockAssistant;
document.getElementById('assistantToggle').onclick = openStockAssistant;
```

The existing AI drawer toggle binding must be removed so the button never opens the copied assistant drawer.

- [ ] **Step 5: Remove copied assistant content and its event handlers**

Remove the copied page's `#assistantScrim`, `#assistant`, `#assistantForm`, memory dialog markup, assistant-only CSS selectors, and the functions/bindings that implement `openAssistant`, `closeAssistant`, `toggleAssistant`, `sendAssistantMessage`, and assistant-memory operations. Keep the `#assistantToggle` button itself and its visual classes so it remains a visible entry button.

- [ ] **Step 6: Preserve the copied资讯业务 logic and run the test**

Do not change the copied page's refresh, article rendering, market, research, watchlist, alert, source, or data.js logic. The only behavior changes in this task are the two navigation bindings and removal of the copied assistant drawer.

Run:

```powershell
python -m pytest tests/test_stock_assistant_entry.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit the copied-page entry change**

```powershell
git add -- apps/news-service/index.html apps/news-service/tests/test_stock_assistant_entry.py
git commit -m "feat: route news entries to stock assistant"
```

### Task 3: Expose a stable current-project view switch without touching AgentWorkspace

**Files:**
- Create: `apps/renderer/src/InvestmentNewsFrame.tsx`
- Create: `apps/renderer/src/InvestmentNewsFrame.css`
- Modify: `apps/renderer/src/App.tsx` only at the root view selection boundary around `function App` and the existing `if (showAgent)` return

- [ ] **Step 1: Add the iframe wrapper component**

Create `apps/renderer/src/InvestmentNewsFrame.tsx` with:

```tsx
import "./InvestmentNewsFrame.css";

export default function InvestmentNewsFrame() {
  return (
    <main className="investment-news-frame" aria-label="资讯看板">
      <iframe
        className="investment-news-frame__content"
        title="投资资讯"
        src="http://127.0.0.1:8888/index.html"
      />
    </main>
  );
}
```

- [ ] **Step 2: Add frame-only layout CSS**

Create `apps/renderer/src/InvestmentNewsFrame.css`:

```css
.investment-news-frame {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #111927;
}

.investment-news-frame__content {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}
```

- [ ] **Step 3: Replace only the old root News App with a URL view selector**

Delete the old `function App()` news implementation at the end of `App.tsx`, but do not edit the preceding `AgentWorkspace` function. Remove the now-unused news-only types `Taxonomy`, `NewsItem`, `NewsResponse`, `SourceHealth`, and `NewsSubscription`. Keep shared helpers such as `formatDate` because the assistant uses them.

Import `InvestmentNewsFrame` and add this root implementation:

```tsx
type RootView = "news" | "agent";

function readRootView(): RootView {
  return new URLSearchParams(window.location.search).get("view") === "agent"
    ? "agent"
    : "news";
}

function App() {
  const [view, setView] = useState<RootView>(readRootView);

  useEffect(() => {
    const onPopState = () => setView(readRootView());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigateToNews = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("view");
    window.history.pushState({}, "", url);
    setView("news");
  };

  if (view === "agent") {
    return <AgentWorkspace onOpenNews={navigateToNews} />;
  }

  return <InvestmentNewsFrame />;
}
```

Keep the existing `AgentWorkspace` function body unchanged. The only existing assistant-side callback change allowed is passing the already-defined `onOpenNews` callback from the root selector.

- [ ] **Step 4: Verify the old React news JSX is unreachable**

Run:

```powershell
rg -n "return \(<main className=\"news-app\"|AgentWorkspace|InvestmentNewsFrame" apps/renderer/src/App.tsx
```

Expected: `AgentWorkspace` remains defined and referenced by the agent branch; `InvestmentNewsFrame` is returned by the news branch; the old `news-app` JSX no longer exists.

- [ ] **Step 5: Commit the root view switch**

```powershell
git add -- apps/renderer/src/App.tsx apps/renderer/src/InvestmentNewsFrame.tsx apps/renderer/src/InvestmentNewsFrame.css
git commit -m "feat: replace news view with investment news frame"
```

### Task 4: Remove the obsolete current-project资讯 API surface

**Files:**
- Modify: `apps/backend/app/main.py` only in the old资讯 route block
- Do not modify: any `/agent/*` route, memory module, model settings route, scheduler, or stock research implementation

- [ ] **Step 1: Record the assistant route set before editing**

Run:

```powershell
rg -n '^@app\.(get|post|put|delete)\("/agent/' apps/backend/app/main.py > "$env:TEMP\agent-routes-before.txt"
```

Expected: a route list file exists and contains all current `/agent/` routes.

- [ ] **Step 2: Remove only the obsolete news routes**

Delete the old route functions for `/taxonomy`, `/sources`, `/news`, `/news/{news_id}/read`, `/news/subscriptions`, and `/refresh` that were used only by the old React news view. Keep shared database helpers only if an `/agent/*` route still imports them; do not remove shared stock or memory helpers.

- [ ] **Step 3: Confirm assistant routes are byte-for-byte unchanged**

Run:

```powershell
rg -n '^@app\.(get|post|put|delete)\("/agent/' apps/backend/app/main.py > "$env:TEMP\agent-routes-after.txt"
Compare-Object (Get-Content "$env:TEMP\agent-routes-before.txt") (Get-Content "$env:TEMP\agent-routes-after.txt")
```

Expected: no differences.

- [ ] **Step 4: Commit the obsolete-route removal**

```powershell
git add -- apps/backend/app/main.py
git commit -m "refactor: remove obsolete news endpoints"
```

### Task 5: Run focused verification and show the migrated result

**Files:**
- Test: `apps/renderer` build output and browser routes
- Test: copied news service on port 8888
- Test: current stock assistant on port 5174 with backend 8000

- [ ] **Step 1: Start the copied资讯 backend for verification**

Run from a separate terminal:

```powershell
python server.py 8888
```

Working directory: `D:\新搭建\apps\news-service`.

Expected: `http://127.0.0.1:8888/index.html` serves the copied资讯 page.

- [ ] **Step 2: Build the unchanged assistant-capable renderer**

Run:

```powershell
npm run build
```

Working directory: `D:\新搭建\apps\renderer`.

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 3: Verify the three required browser states**

Check:

1. `http://127.0.0.1:5174/` shows the copied资讯 page.
2. The left “行情工作台” entry is absent and “股票助手” is present.
3. The blue AI button has no drawer behavior and navigates the current tab to `http://127.0.0.1:5174/?view=agent`.
4. The stock assistant loads and its existing conversation/model/memory controls remain available.
5. The assistant's return-to-news action removes `view=agent` and returns to the copied资讯 page.

- [ ] **Step 4: Confirm no assistant-side files were changed unintentionally**

Run:

```powershell
git diff HEAD~4..HEAD --name-only
git diff HEAD~4..HEAD -- apps/renderer/src/App.tsx apps/backend/app/main.py
```

Expected: only the root view boundary in `App.tsx` and the obsolete news route block in `main.py` differ; no `AgentWorkspace` body or `/agent/*` route changes appear.

- [ ] **Step 5: Commit verification notes only after checks pass**

```powershell
git status --short --branch
```

Expected: no uncommitted migration files except intentionally generated build artifacts ignored by the existing `.gitignore`.
