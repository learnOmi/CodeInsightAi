"use client";

import { cn } from "@/utils";

/**
 * 框架标签配色规则
 *
 * 每条规则包含一组前缀（小写匹配）与对应的 Tailwind 配色类。
 * 匹配时按数组顺序遍历，命中第一条即返回；未命中则使用默认配色。
 *
 * 配色风格参考 NODE_TYPE_CONFIG（见 packages/shared/src/constants.ts）。
 */
interface FrameworkTagRule {
  /** 命中该规则所需的前缀列表（小写） */
  prefixes: string[];
  /** Tailwind 背景与文字颜色类 */
  color: string;
}

const FRAMEWORK_TAG_RULES: FrameworkTagRule[] = [
  // React 系：蓝色
  { prefixes: ["react-"], color: "bg-[var(--color-fw-react)]/15 text-[var(--color-fw-react)]" },
  // Vue 系：绿色
  { prefixes: ["vue-"], color: "bg-[var(--color-fw-vue)]/15 text-[var(--color-fw-vue)]" },
  // Angular 系：红色
  { prefixes: ["angular-"], color: "bg-[var(--color-fw-angular)]/15 text-[var(--color-fw-angular)]" },
  // HTTP / API：紫色
  { prefixes: ["http-controller", "api-endpoint"], color: "bg-[var(--color-fw-default)]/15 text-[var(--color-fw-default)]" },
  // 业务服务 / 数据仓储：青色
  { prefixes: ["business-service", "data-repository"], color: "bg-[var(--color-fw-spring)]/15 text-[var(--color-fw-spring)]" },
  // Flask / FastAPI：橙色
  { prefixes: ["flask-", "fastapi-"], color: "bg-[var(--color-fw-fastapi)]/15 text-[var(--color-fw-fastapi)]" },
  // Express / Koa：黄色（amber）
  { prefixes: ["express-", "koa-"], color: "bg-[var(--color-fw-express)]/15 text-[var(--color-fw-express)]" },
  // 通用工程语义：灰色
  {
    prefixes: ["dependency-injection", "transactional", "scheduled-task"],
    color: "bg-[var(--color-fw-default)]/15 text-[var(--color-fw-default)]",
  },
];

const FRAMEWORK_TAG_DEFAULT_COLOR = "bg-gray-500/15 text-gray-500";

/**
 * 根据 tag 名称获取对应的 Tailwind 配色类
 *
 * @param tag 框架标签名称
 * @returns Tailwind 颜色类字符串
 */
function getFrameworkTagColor(tag: string): string {
  const lower = tag.toLowerCase();
  for (const rule of FRAMEWORK_TAG_RULES) {
    if (rule.prefixes.some((prefix) => lower.startsWith(prefix))) {
      return rule.color;
    }
  }
  return FRAMEWORK_TAG_DEFAULT_COLOR;
}

interface FrameworkBadgeProps {
  /** 框架标签列表 */
  tags: string[];
}

/**
 * 框架标签展示组件
 *
 * 以小尺寸 chip 样式渲染一组框架标签，根据标签名称前缀分配不同颜色。
 * 通常显示在节点名称之后，用于标识节点所属的框架或承担的工程语义。
 */
export function FrameworkBadge({ tags }: FrameworkBadgeProps) {
  if (!tags || tags.length === 0) {
    return null;
  }

  return (
    <span className="inline-flex items-center gap-1 flex-wrap">
      {tags.map((tag) => (
        <span
          key={tag}
          className={cn(
            "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium leading-none",
            getFrameworkTagColor(tag)
          )}
        >
          {tag}
        </span>
      ))}
    </span>
  );
}
