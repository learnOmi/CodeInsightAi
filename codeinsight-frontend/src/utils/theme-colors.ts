/**
 * 主题色工具 — 将硬编码色值统一映射到 CSS 变量，支持亮/暗主题自动适配。
 */

// ── 调用图节点类型色 ────────────────────────────────
export function getNodeColor(nodeType: string): string {
  const map: Record<string, string> = {
    function:      "var(--color-node-function)",
    method:        "var(--color-node-method)",
    constructor:   "var(--color-node-constructor)",
    class:         "var(--color-node-class)",
    interface:     "var(--color-node-interface)",
    enum:          "var(--color-node-enum)",
    struct:        "var(--color-node-struct)",
    call:          "var(--color-node-call)",
    external:      "var(--color-node-external)",
  };
  return map[nodeType] ?? "var(--color-node-call)";
}

export function getNodeBorderColor(nodeType: string, selected: boolean): string {
  if (selected) return "var(--color-status-info)";
  return `${getNodeColor(nodeType)}80`; // 50% opacity hex suffix
}

export function getNodeBgColor(nodeType: string, isRoot: boolean): string {
  if (isRoot) return `hsla(from ${getNodeColor(nodeType)} h s l / 0.12)`;
  return "transparent";
}

// ── 调用边类型色 ────────────────────────────────────
export function getEdgeColor(callType: string): string {
  const map: Record<string, string> = {
    static:   "var(--color-edge-static)",
    dynamic:  "var(--color-edge-dynamic)",
    unknown:  "var(--color-edge-unknown)",
    external: "var(--color-edge-external)",
    injected: "var(--color-edge-injected)",
  };
  return map[callType] ?? "var(--color-edge-unknown)";
}

// ── 框架标签色 ──────────────────────────────────────
const FW_PREFIX_MAPS: Array<{ prefixes: string[]; cssVar: string }> = [
  { prefixes: ["react-"], cssVar: "--color-fw-react" },
  { prefixes: ["vue-"], cssVar: "--color-fw-vue" },
  { prefixes: ["angular-"], cssVar: "--color-fw-angular" },
  { prefixes: ["spring", "jpa", "mybatis", "typeorm"], cssVar: "--color-fw-spring" },
  { prefixes: ["express-", "koa-"], cssVar: "--color-fw-express" },
  { prefixes: ["flask-", "fastapi-"], cssVar: "--color-fw-fastapi" },
];

export function getFrameworkTagColor(tag: string): string {
  const lower = tag.toLowerCase();
  for (const rule of FW_PREFIX_MAPS) {
    if (rule.prefixes.some((prefix) => lower.startsWith(prefix))) {
      return `bg-[var(${rule.cssVar})]/15 text-[var(${rule.cssVar})]`;
    }
  }
  return "bg-[var(--color-fw-default)]/15 text-[var(--color-fw-default)]";
}

// ── 中间件类型色 ────────────────────────────────────
export function getMiddlewareStyle(type: string): { bg: string; border: string; text: string; badgeBg: string; badgeText: string } {
  const map: Record<string, { bg: string; border: string; text: string; badgeBg: string; badgeText: string }> = {
    authentication: {
      bg: "hsl(0 84% 60% / 0.08)",
      border: "var(--color-mw-auth)",
      text: "hsl(0 60% 40%)",
      badgeBg: "hsl(0 84% 60% / 0.15)",
      badgeText: "var(--color-mw-auth)",
    },
    rate_limiting: {
      bg: "hsl(24 94% 50% / 0.08)",
      border: "var(--color-mw-rate-limit)",
      text: "hsl(24 70% 40%)",
      badgeBg: "hsl(24 94% 50% / 0.15)",
      badgeText: "var(--color-mw-rate-limit)",
    },
    logging: {
      bg: "hsl(217 91% 60% / 0.08)",
      border: "var(--color-mw-logging)",
      text: "hsl(217 70% 40%)",
      badgeBg: "hsl(217 91% 60% / 0.15)",
      badgeText: "var(--color-mw-logging)",
    },
    cors: {
      bg: "hsl(152 71% 48% / 0.08)",
      border: "var(--color-mw-cors)",
      text: "hsl(152 60% 35%)",
      badgeBg: "hsl(152 71% 48% / 0.15)",
      badgeText: "var(--color-mw-cors)",
    },
  };
  return map[type] ?? {
    bg: "hsl(215 10% 47% / 0.08)",
    border: "var(--text-muted)",
    text: "var(--text-secondary)",
    badgeBg: "hsl(215 10% 47% / 0.15)",
    badgeText: "var(--text-muted)",
  };
}

// ── HTTP 方法色 ─────────────────────────────────────
export function getMethodTagStyle(method: string): string {
  const map: Record<string, string> = {
    GET:    "bg-status-success/15 text-status-success",
    POST:   "bg-status-info/15 text-status-info",
    PUT:    "bg-status-warning/15 text-status-warning",
    DELETE: "bg-status-error/15 text-status-error",
    PATCH:  "bg-purple-500/15 text-purple-500",
  };
  return map[method.toUpperCase()] ?? "bg-gray-500/15 text-gray-500";
}

// ── 作用域色 ────────────────────────────────────────
export function getScopeTagStyle(scope: string): string {
  const map: Record<string, string> = {
    compile: "bg-status-info/15 text-status-info",
    dev:     "bg-status-warning/15 text-status-warning",
    test:    "bg-status-success/15 text-status-success",
    peer:    "bg-purple-500/15 text-purple-500",
  };
  return map[scope.toLowerCase()] ?? "bg-gray-500/15 text-gray-500";
}

// ── 框架分类色 ──────────────────────────────────────
export function getFrameworkCategoryColor(category: string): string {
  const map: Record<string, string> = {
    frontend:   "bg-[var(--color-fw-react)]/15 text-[var(--color-fw-react)]",
    backend:    "bg-[var(--color-node-method)]/15 text-[var(--color-node-method)]",
    database:   "bg-status-success/15 text-status-success",
    messaging:  "bg-status-warning/15 text-status-warning",
    testing:    "bg-yellow-500/15 text-yellow-500",
    build:      "bg-cyan-500/15 text-cyan-500",
    other:      "bg-gray-500/15 text-gray-500",
  };
  return map[category] ?? "bg-gray-500/15 text-gray-500";
}
