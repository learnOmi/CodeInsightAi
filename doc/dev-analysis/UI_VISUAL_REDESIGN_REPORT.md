# CodeInsight AI — 视觉升级报告：从"功能可用"到 Raycast 级别审美

> 目标：让 CodeInsight 的视觉品质达到 Raycast / Linear / Vercel 的水平。
> 范围：亮/暗双主题，Tailwind CSS v4 + Framer Motion 技术栈。

---

## 一、现状诊断

### 1.1 当前视觉层级评分

| 维度 | 当前评分 | Raycast 对标 | 差距 |
|------|---------|-------------|------|
| 背景质感 | ★★☆☆☆ | ★★★★★ | 纯平色块 vs 噪点+渐变 |
| 卡片深度 | ★★☆☆☆ | ★★★★★ | 灰色投影 vs 彩色辉光 |
| 边框处理 | ★★☆☆☆ | ★★★★★ | 纯色描边 vs 渐变边框 |
| 排版层次 | ★★☆☆☆ | ★★★★★ | 字号差小 vs 极端对比 |
| 色彩活力 | ★★★☆☆ | ★★★★★ | 安全色 vs 高饱和品牌色 |
| 微交互 | ★★★☆☆ | ★★★★★ | hover 变色 vs 物理级反馈 |
| 毛玻璃效果 | ★★☆☆☆ | ★★★★★ | 无 vs 全局 backdrop-blur |

**综合评分：2.1 / 5.0** — 功能性完整，但缺乏"第一眼惊艳感"。

### 1.2 核心问题根因

```
┌─────────────────────────────────────────────────────────────┐
│  问题1: "灰白卡片" 模式                                       │
│  所有组件 = 白色/深灰卡片 + 灰色边框 + 灰色阴影                │
│  缺少：渐变边框、彩色辉光、噪点纹理                            │
├─────────────────────────────────────────────────────────────┤
│  问题2: 排版层级扁平                                          │
│  h1=4xl, h2=xl, body=sm — 字号差只有 1 级                    │
│  Raycast: 标题 3xl/4xl + 标签 9px/10px — 字号差 3 级           │
├─────────────────────────────────────────────────────────────┤
│  问题3: 色彩保守                                              │
│  品牌色仅用于按钮和链接，占比 <5%                               │
│  Raycast: 品牌色贯穿导航栏、选中态、图标、辉光、渐变              │
├─────────────────────────────────────────────────────────────┤
│  问题4: 缺少材质感                                             │
│  没有 backdrop-blur, 没有内发光, 没有噪点叠加                   │
│  所有元素都是"平面贴上去"的感觉                                 │
├─────────────────────────────────────────────────────────────┤
│  问题5: 动画单一                                              │
│  只有 hover:translate-y + opacity 变化                         │
│  Raycast: 弹簧曲线、staggered entrance、物理惯性                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、Raycast 审美解构

### 2.1 背景系统（最关键的差异）

Raycast 的背景不是纯色——它有三层：

```
Layer 0: 深色基底 #0B0F19 (接近黑蓝)
Layer 1: 噪点纹理 overlay (opacity 3%) — 消除"死黑"感
Layer 2: 径向渐变光晕 (brand purple, opacity 8%, 屏幕中心)
```

**当前问题：** `--bg-base: #0f172a` 纯平深蓝，像未完成的草稿。

**改造方案：**

```tsx
// RootLayout.tsx — 在 body 内添加独立噪点层（避免使用 ::before 与 React Flow canvas 冲突）
<body className="...">
  {/* 噪点纹理层 — 独立 DOM 元素，避免 z-index 冲突 */}
  <div className="pointer-events-none fixed inset-0 z-0 opacity-[0.03] dark:opacity-[0.02]"
       style={{
         backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
         backgroundSize: "200px 200px",
       }} />
  {/* 品牌光晕 — 暗色模式下屏幕顶部紫色辉光 */}
  <div className="pointer-events-none fixed inset-0 z-0 dark:bg-[radial-gradient(ellipse_at_50%_0%,hsla(247,84%,59%,0.08),transparent_60%)]" />

  <main className="relative z-1">{children}</main>
</body>
```

**注意：**
- 用 `fixed inset-0` 独立 `<div>` 而非 `body::before`，避免 `z-index` 与 React Flow 的 canvas 渲染冲突
- 噪点频率 `baseFrequency='0.65'` 比原方案 0.9 更低，纹理更细腻

### 2.2 渐变边框（Gradient Borders）

Raycast 的卡片边框不是 `border-1px solid #333`——它是渐变的：

```
top-left: brand-purple → top-right: brand-blue → bottom: transparent
```

**当前问题：** `border border-[var(--border)]` 纯色描边，像表格线。

**改造方案：** 用 `background-clip` + 伪元素实现渐变边框：

```tsx
// 通用渐变边框卡片 — 仅对低频容器卡片使用
<div className="group relative rounded-2xl overflow-hidden">
  {/* 渐变边框层 — hover 时显现 */}
  <div className="absolute inset-0 rounded-2xl 
                  bg-gradient-to-br from-brand/40 via-brand/10 to-transparent 
                  opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
  {/* 内容层 — 微内缩以露出边框 */}
  <div className="relative m-[1px] rounded-2xl bg-[var(--bg-card)] p-6">
    ...
  </div>
</div>
```

**限制：** 不建议用于 CallGraph 节点（数量多，DOM 膨胀），仅用于 RepoCard、首页卡片、设置面板等低频容器。

### 2.3 彩色辉光阴影（Colored Glow Shadows）

Raycast hover 时不是变灰——是发出该元素的彩色光：

```
RepoCard hover → 紫色辉光 (brand purple, blur 24px, opacity 15%)
```

**当前问题：** `shadow-md` 是灰色投影，毫无个性。

**改造方案：** 在 `@theme` 中注入自定义阴影，组件中直接用 Tailwind class：

```css
/* globals.css 已实现 */
@theme {
  --shadow-glow-brand-light: 0 0 24px hsla(247,84%,59%,0.15), 0 0 48px hsla(247,84%,59%,0.08);
  --shadow-glow-focus: 0 0 0 2px hsla(247,84%,59%,0.3);
}
```

```tsx
<div className="group transition-all duration-500 hover:-translate-y-1 hover:shadow-[var(--shadow-glow-brand-light)]">
```

### 2.4 排版层级（Typography Scale）

Raycast 的字号差极大：

```
页面标题:    40px / 700 / tracking-tight
卡片标题:    16px / 600
正文:        14px / 400
辅助文字:    12px / 500 / uppercase / tracking-wider
标签/徽章:   10px / 600 / tracking-wide
```

**当前问题：** 最大字号差只有 2 级（4xl→text-xs），标签文字仍然 12px+。

**改造方案：**

```tsx
// 页面标题
<h1 className="text-5xl font-bold tracking-tight text-[var(--text-primary)]">
  CodeInsight AI
</h1>

// 副标题
<p className="mt-2 text-sm text-[var(--text-muted)] tracking-wide">
  AI 驱动的代码知识提取与可视化分析平台
</p>

// 卡片标题（加大对比）
<div className="text-lg font-semibold text-[var(--text-primary)]">仓库管理</div>

// 分类标签（极致缩小）
<span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
  ANALYSIS
</span>
```

**⚠ 可访问性注意：** `text-[9px]` 仅用于纯装饰性标签（如 `NEW`、`FILES` 等 uppercase 短标签），内容性文字至少 11-12px。

### 2.5 毛玻璃效果（Backdrop Blur）

Raycast 大量使用 `backdrop-blur-xl`：

```
导航栏:     backdrop-blur-xl bg-black/60
Modal:      backdrop-blur-md bg-black/70
面板:       backdrop-blur-lg bg-[var(--bg-card)]/80
```

**当前问题：** 仅 CallChainPanel Modal 有 `backdrop-blur-sm`，几乎可以忽略。

**改造方案：**

```tsx
// 顶部导航栏
<header className="sticky top-0 z-10 
                   bg-[var(--bg-card)]/70 backdrop-blur-xl 
                   border-b border-white/[0.06]">
```

```tsx
// Modal 遮罩
<div className="fixed inset-0 z-50 flex items-center justify-center">
  <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
  <div className="relative bg-[var(--bg-card)] rounded-2xl shadow-2xl 
                  border border-white/[0.08]">
```

### 2.6 间距呼吸感

Raycast 的间距比常规设计大 20-30%：

```
卡片内边距:  p-6 (24px) → p-8 (32px)
卡片间距:    gap-6 (24px) → gap-8 (32px)
段落间距:    space-y-4 → space-y-6
标题下间距:  mb-4 → mb-6
```

**当前问题：** 大部分组件 `p-5` `gap-4`，信息密度过高。

---

## 三、逐组件改造方案

### 3.1 首页 (page.tsx) — 第一印象

**现状：** 标题渐变 + 三个平铺卡片 + 快速开始步骤。

**Raycast 化方案：**

```tsx
// 1. 标题区域 — 增加光晕背景
<header className="mb-16 relative">
  {/* 标题后方光晕 */}
  <div className="absolute -top-8 -left-8 w-64 h-64 rounded-full 
                  bg-brand/10 blur-[100px] pointer-events-none" />
  
  <h1 className="text-5xl font-bold tracking-tight relative">
    <span className="bg-gradient-to-r from-brand via-brand-fg to-accent2 
                     bg-clip-text text-transparent">
      CodeInsight AI
    </span>
  </h1>
  <p className="mt-4 text-base text-[var(--text-muted)] max-w-lg leading-relaxed">
    AI 驱动的代码知识提取与可视化分析平台
  </p>
</header>

// 2. 导航卡片 — 渐变边框 + 辉光
<section className="mb-16 grid gap-6 sm:grid-cols-3">
  <Link href="/repositories"
        className="group relative rounded-2xl overflow-hidden 
                   bg-[var(--bg-card)] p-8 transition-all duration-500
                   hover:-translate-y-2 hover:shadow-[var(--shadow-glow-brand-light)]">
    {/* 渐变边框 */}
    <div className="absolute inset-0 rounded-2xl 
                    bg-gradient-to-br from-brand/30 via-brand/5 to-transparent 
                    opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
    {/* 顶部光条 */}
    <div className="absolute inset-x-0 top-0 h-px 
                    bg-gradient-to-r from-transparent via-brand/60 to-transparent 
                    opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
    
    <div className="relative">
      <div className="text-[10px] font-semibold uppercase tracking-widest 
                      text-[var(--text-muted)] mb-3">Navigation</div>
      <div className="text-xl font-semibold text-[var(--text-primary)] 
                      group-hover:text-brand transition-colors">
        仓库管理
      </div>
      <p className="mt-2 text-sm text-[var(--text-muted)] leading-relaxed">
        添加代码仓库，启动 AI 分析
      </p>
      {/* 箭头指示 */}
      <div className="mt-4 flex items-center gap-1 text-[10px] 
                      text-[var(--text-muted)] group-hover:text-brand transition-colors">
        <span>进入</span>
        <span className="transform group-hover:translate-x-0.5 transition-transform">→</span>
      </div>
    </div>
  </Link>
</section>

// 3. 快速开始 — 改为步骤线样式
<section className="rounded-2xl bg-[var(--bg-card)] border border-white/[0.06] p-8">
  <div className="text-[10px] font-semibold uppercase tracking-widest 
                  text-[var(--text-muted)] mb-6">Getting Started</div>
  <ol className="space-y-6">
    <li className="flex items-start gap-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center 
                      rounded-full bg-brand/10 text-sm font-semibold text-brand 
                      ring-1 ring-brand/20">1</div>
      <div>
        <div className="text-sm font-medium text-[var(--text-primary)]">添加本地仓库路径</div>
        <div className="text-xs text-[var(--text-muted)] mt-0.5">支持文件系统目录或 Git URL</div>
      </div>
    </li>
  </ol>
</section>
```

**关键变化：**
- 标题字号 `4xl → 5xl`，增加光晕背景
- 卡片标题加 `uppercase tracking-widest` 分类标签
- 渐变边框通过双 div 实现
- 增加 `→` 箭头指示交互
- 快速开始步骤增加详细说明文字
- 间距全面放大：`p-6 → p-8`, `gap-4 → gap-6`

### 3.2 RepoCard — 核心卡片

**现状：** `rounded-xl border border-[var(--border)]` + 顶部光晕线。

**Raycast 化方案：**

```tsx
// 目前 RepoCard.tsx 实现
<div className="group relative rounded-2xl overflow-hidden 
                bg-[var(--bg-card)] transition-all duration-500
                hover:-translate-y-1 hover:shadow-[var(--shadow-glow-brand-light)]">
  {/* 渐变边框层 — hover 时显现 */}
  <div className="absolute inset-0 rounded-2xl 
                  bg-gradient-to-b from-brand/20 via-brand/5 to-transparent 
                  opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
  
  {/* 内容 */}
  <div className="relative p-6">
    {/* 顶部：仓库名 + 状态 */}
    <div className="flex items-start justify-between gap-3 mb-4">
      <div className="min-w-0 flex-1">
        <Link to={repoUrl} className="text-base font-semibold 
                text-[var(--text-primary)] hover:text-brand transition-colors 
                truncate block">
          {name}
        </Link>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)] font-mono truncate opacity-70">
          {path}
        </p>
      </div>
      <StatusBadge status={status} variant="compact" />
    </div>
    
    {/* 进度条 — 更细 */}
    {analyzing && (
      <div className="mb-4 space-y-1.5">
        <div className="flex justify-between text-[11px]">
          <span className="text-[var(--text-muted)]">{currentStep}</span>
          <span className="font-mono tabular-nums text-[var(--text-muted)]">{percent}%</span>
        </div>
        <div className="h-1 bg-[var(--bg-hover)] rounded-full overflow-hidden">
          <div className="h-full rounded-full bg-gradient-to-r from-brand to-brand-fg transition-all"
               style={{ width: `${percent}%` }} />
        </div>
      </div>
    )}
    
    {/* 统计行 — 英文大写 + 更细字号 */}
    <div className="grid grid-cols-3 divide-x divide-[var(--border)]/50 mb-5">
      <StatItem value={fileCount} label="FILES" />
      <StatItem value={lineCount} label="LINES" />
      <StatItem value={knowledgePointsCount} label="INSIGHTS" />
    </div>
  </div>
</div>
```

**关键变化：**
- 圆角 `xl → 2xl`（16px）
- 渐变边框层（hover 时从顶部透出紫色渐变）
- 统计标签改为英文大写（"文件" → "FILES"），字号 11px
- 按钮区域减少，留白增加
- 路径文字降低透明度 `opacity-70`，减少视觉噪音

### 3.3 StatusBadge — 状态徽标

```tsx
export function StatusBadge({ status, variant = "default" }: { status: string; variant?: "default" | "compact" }) {
  const config = getAnalysisStatusConfig(status);
  
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold tracking-wide
      ${variant === "compact" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs"}
      ${config.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${config.animate ? "animate-pulse" : ""}`} 
            style={{ backgroundColor: "currentColor" }} />
      {config.label}
    </span>
  );
}
```

**关键变化：**
- 增加 `tracking-wide`
- 状态点从图标改为纯色圆点 `w-1.5 h-1.5`
- 紧凑版 `text-[10px]`（保持可读性，放弃 9px）

### 3.4 框架列表 & 依赖列表 — 数据密集区域

这些区域需要**更高的信息密度 + 更强的分组感**：

```tsx
<div className="group relative rounded-xl overflow-hidden 
                bg-[var(--bg-card)] border border-white/[0.06] 
                p-4 transition-all duration-300
                hover:border-brand/20 hover:shadow-[var(--shadow-glow-brand-light)]/50">
  {/* 顶部渐变 */}
  <div className="absolute inset-x-0 top-0 h-px 
                  bg-gradient-to-r from-transparent via-brand/40 to-transparent 
                  opacity-0 group-hover:opacity-100 transition-opacity" />
  
  <div className="flex items-center justify-between mb-3">
    <span className="text-sm font-semibold text-[var(--text-primary)] 
                     group-hover:text-brand transition-colors">
      {displayName}
    </span>
    <span className="text-[10px] font-semibold uppercase tracking-widest 
                     px-2 py-0.5 rounded-full bg-[var(--bg-hover)] text-[var(--text-muted)]">
      {categoryLabel}
    </span>
  </div>
  
  {/* 置信度条 — 更细 */}
  <div className="flex items-center gap-2 mb-3">
    <div className="flex-1 h-0.5 bg-[var(--bg-hover)] rounded-full overflow-hidden">
      <div className="h-full bg-gradient-to-r from-brand to-brand-fg rounded-full transition-all"
           style={{ width: `${confidence * 100}%` }} />
    </div>
    <span className="text-[10px] font-mono tabular-nums text-[var(--text-muted)]">
      {(confidence * 100).toFixed(0)}%
    </span>
  </div>
</div>
```

**关键变化：**
- 置信度条高度 `h-1 → h-0.5`（更精致）
- 分类标签 `text-[10px] uppercase tracking-widest`
- 边框 `border-white/[0.06]`（极淡，暗色模式下可见）
- 顶部渐变光条

### 3.5 CallGraph — 可视化区域

调用图是**整个应用最复杂也最容易出彩**的区域，但改造需谨慎：

```tsx
// 节点 — 磨砂玻璃 + 彩色边框（使用兼容的 CSS 方案）
<motion.div
  className="relative rounded-xl backdrop-blur-md cursor-pointer select-none"
  style={{
    width: NODE_W, height: NODE_H,
    // 使用当前 theme-colors.ts 的 nodeColor 映射方案，而非 CSS hsla(from...) 相对颜色语法
    backgroundColor: `${cfg.nodeBg || cfg.color}18`,
    border: `1px solid ${selected ? "var(--color-status-info)" : (cfg.color + "40")}`,
    boxShadow: selected 
      ? `0 0 0 2px hsla(247,84%,59%,0.3), 0 0 20px ${cfg.color}26`
      : "0 1px 2px rgba(0,0,0,0.05)",
  }}
>
```

**⚠ 浏览器兼容：** 不使用 `hsla(from var(--x) h s l / a)` CSS 相对颜色语法（2024 年新规范，兼容性不足），改用当前 `theme-colors.ts` 已有的节点色映射 + JS 拼接透明度。

**关键变化：**
- `backdrop-blur-md` 磨砂玻璃
- 边框 `1px` + 半透明色（`#color40` = 25% 不透明）
- 选中态双重阴影：focus ring + 彩色辉光
- 非当前文件节点透明度降低

### 3.6 导航栏 & 面板

```tsx
// 顶部导航栏
<header className="sticky top-0 z-10 
                   bg-[var(--bg-card)]/70 backdrop-blur-xl 
                   border-b border-white/[0.06]">
  <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-3">
    <Link href="/repositories" className="text-sm text-[var(--text-muted)] 
                                           hover:text-[var(--text-primary)] transition-colors">
      ← 仓库列表
    </Link>
    <div className="h-4 w-px bg-[var(--border)]/50" />
    <h1 className="text-sm font-semibold text-[var(--text-primary)] tracking-tight">
      {repo?.name ?? "加载中..."}
    </h1>
  </div>
</header>
```

**关键变化：**
- `backdrop-blur-xl` 强模糊
- 背景半透明 `bg-[var(--bg-card)]/70`
- 边框极淡 `border-white/[0.06]`
- 分隔线 `h-4 w-px` 而非 `h-5`

---

## 四、全局 CSS 增强

### 4.1 噪点纹理 + 品牌光晕

已集成到 `RootLayout`（参见 2.1），使用独立 DOM 元素而非 `::before`。

### 4.2 滚动条美化

```css
/* globals.css */
/* 自定义滚动条 — Raycast 风格极细滚动条 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* Firefox 支持 */
* {
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
```

### 4.3 选中文字颜色

```css
/* globals.css */
::selection {
  background: hsla(247, 84%, 59%, 0.3);
  color: var(--text-primary);
}
```

---

## 五、已就绪的基础设施

以下内容已在之前的迭代中完成，报告不再重复：

| 基础设施 | 文件 | 说明 |
|---------|------|------|
| 亮/暗 CSS 变量 | `globals.css` | `:root` + `.dark` 双主题变量 |
| 品牌色 & 节点色 | `globals.css` `@theme` | brand, accent, node-*, edge-*, framework-* |
| 彩色辉光阴影 | `globals.css` `@theme` | `--shadow-glow-brand-light`, `--shadow-glow-focus` |
| 颜色工具函数 | `theme-colors.ts` | 节点/边/框架/中间件取色映射 |
| NavTrailBar 升级 | `NavTrailBar.tsx` | Photoshop 式历史记录 |
| 文件树自动展开 | `FileTree.tsx` | useEffect 监听 selectedFilePath |
| 调用图悬浮球 | `CallGraph.tsx` | 左侧节点列表悬浮球 |
| 节点数上限准确判断 | `CallGraph.tsx` | 区分无新调用者 vs 真正达上限 |

---

## 六、实施计划

### Phase A: 背景与材质（0.5h）

| 任务 | 文件 | 改动 |
|------|------|------|
| 噪点纹理层 | `layout.tsx` | 在 `<body>` 内添加独立噪点 div |
| 品牌光晕层 | `layout.tsx` | 暗色模式径向渐变光晕 div |
| 自定义滚动条 | `globals.css` | `::-webkit-scrollbar` + Firefox `scrollbar-width` |
| 选中文字颜色 | `globals.css` | `::selection` 品牌色 |

### Phase B: 首页毛玻璃 + 卡片升级（1h）

| 任务 | 文件 | 改动 |
|------|------|------|
| 导航栏毛玻璃 | `Navbar.tsx` | `backdrop-blur-xl` + 半透明背景 |
| 首页标题光晕 | `page.tsx` | 标题字号 5xl + 品牌光晕 div |
| 首页卡片渐变边框 | `page.tsx` | 双 div 渐变边框 + 辉光 hover |
| 首页快速开始 | `page.tsx` | 步骤线样式 + 间距放大 |

### Phase C: RepoCard 升级（1h）

| 任务 | 文件 | 改动 |
|------|------|------|
| 渐变边框 | `RepoCard.tsx` | 双 div 渐变边框层 |
| 辉光 hover | `RepoCard.tsx` | `hover:shadow-[var(--shadow-glow-brand-light)]` |
| 统计英文大写 | `RepoCard.tsx` | "文件"→"FILES", "行数"→"LINES" |
| 圆角 2xl | `RepoCard.tsx` | `rounded-xl → rounded-2xl` |

### Phase D: 全局排版调优（1h）

| 任务 | 文件 | 改动 |
|------|------|------|
| h1 标题放大 | 各 page.tsx | 统一 `text-5xl font-bold tracking-tight` |
| 标签缩小 uppercase | 各组件 | `text-[10px] uppercase tracking-widest` |
| 间距 +20% | 各卡片 | `p-6 → p-8`, `gap-4 → gap-6` |
| StatusBadge 升级 | `StatusBadge.tsx` | 纯色圆点 + tracking-wide |

---

## 七、设计原则总结

1. **少即是多** — 减少边框数量，用渐变和辉光代替
2. **对比即美** — 标题尽可能大，标签尽可能小
3. **材质分层** — 背景噪点 → 卡片磨砂 → 悬浮辉光，三层深度
4. **品牌贯穿** — 品牌色不只用于按钮，要出现在光晕、边框、选中态、渐变中
5. **物理感** — hover 不是变色，是"浮起来"（translateY + 辉光同时出现）
6. **暗色不黑** — 暗色主题用深蓝灰 `#0f172a` 而非纯黑 `#000`，保持层次

---

## 八、参考截图对照

| 我们的当前状态 | Raycast 目标状态 |
|--------------|----------------|
| 纯白/深灰卡片 | 磨砂玻璃 + 渐变边框 |
| 灰色投影阴影 | 彩色辉光阴影 |
| `text-sm` 标题 | `text-5xl` 标题 + `text-[10px]` 标签 |
| `border-gray-200` | `border-white/[0.06]` |
| 纯色背景 | 噪点 + 径向渐变光晕 |
| 简单 hover 变色 | hover: translateY + 辉光 + 渐变边框同时触发 |