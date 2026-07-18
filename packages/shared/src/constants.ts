/**
 * CodeInsight AI 前端专属常量
 *
 * 类型定义由后端 Pydantic Schema 通过 OpenAPI 自动生成（见 generated.ts）。
 * 本文件仅保留前端需要的常量映射、显示名称等非类型信息。
 */

import type { components } from './generated';

type KnowledgeCategory = components['schemas']['KnowledgeCategory'];

/**
 * 知识点分类显示名称映射
 */
export const KNOWLEDGE_CATEGORY_NAMES: Record<KnowledgeCategory, string> = {
  'DP-': '设计模式',
  'AD-': '架构决策',
  'AL-': '算法实现',
  'ET-': '工程技巧',
  'DK-': '领域知识',
};

/**
 * 知识点分类颜色映射（用于 UI 标签着色）
 */
export const KNOWLEDGE_CATEGORY_COLORS: Record<KnowledgeCategory, string> = {
  'DP-': '#3b82f6', // blue
  'AD-': '#8b5cf6', // purple
  'AL-': '#10b981', // green
  'ET-': '#f59e0b', // amber
  'DK-': '#ef4444', // red
};

/**
 * AST 节点类型显示配置
 */
export interface NodeTypeConfig {
  icon: string;
  color: string;
  label: string;
}

export const NODE_TYPE_CONFIG: Record<string, NodeTypeConfig> = {
  function:      { icon: '⚙️', color: 'bg-[var(--color-node-function)]/15 text-[var(--color-node-function)]', label: '函数' },
  method:        { icon: '⚙️', color: 'bg-[var(--color-node-method)]/15 text-[var(--color-node-method)]', label: '方法' },
  class:         { icon: '🏗️', color: 'bg-[var(--color-node-class)]/15 text-[var(--color-node-class)]', label: '类' },
  interface:     { icon: '📆', color: 'bg-[var(--color-node-interface)]/15 text-[var(--color-node-interface)]', label: '接口' },
  module:        { icon: '📦', color: 'bg-gray-500/15 text-gray-500', label: '模块' },
  variable:      { icon: '📌', color: 'bg-gray-500/15 text-gray-500', label: '变量' },
  import:        { icon: '🔗', color: 'bg-status-success/15 text-status-success', label: '导入' },
  function_call: { icon: '📞', color: 'bg-[var(--color-node-call)]/15 text-[var(--color-node-call)]', label: '调用' },
  call:          { icon: '📞', color: 'bg-[var(--color-node-call)]/15 text-[var(--color-node-call)]', label: '调用' },
  constructor:   { icon: '🏗️', color: 'bg-[var(--color-node-constructor)]/15 text-[var(--color-node-constructor)]', label: '构造器' },
  struct:        { icon: '⚛️', color: 'bg-[var(--color-node-struct)]/15 text-[var(--color-node-struct)]', label: '结构体' },
  enum:          { icon: '📌', color: 'bg-[var(--color-node-enum)]/15 text-[var(--color-node-enum)]', label: '枚举' },
  default:       { icon: '📄', color: 'bg-gray-500/15 text-gray-500', label: '节点' },
};

/**
 * 获取节点类型的显示配置
 */
export function getNodeTypeConfig(nodeType: string): NodeTypeConfig {
  return NODE_TYPE_CONFIG[nodeType] ?? NODE_TYPE_CONFIG.default;
}

/**
 * 分析状态显示配置
 */
export interface AnalysisStatusConfig {
  icon: string;
  label: string;
  color: string;
  animate?: boolean;
}

export const ANALYSIS_STATUS_CONFIG: Record<string, AnalysisStatusConfig> = {
  pending:              { icon: '⏳', label: '待分析', color: 'bg-gray-500/15 text-gray-500' },
  analyzing:            { icon: '🔄', label: '分析中', color: 'bg-status-info/15 text-status-info', animate: true },
  scanning:             { icon: '🔍', label: '扫描中', color: 'bg-status-info/15 text-status-info', animate: true },
  parsing:              { icon: '🧩', label: '解析中', color: 'bg-status-info/15 text-status-info', animate: true },
  analyzing_structures: { icon: '📆', label: '结构分析', color: 'bg-status-info/15 text-status-info', animate: true },
  analyzing_modules:    { icon: '🧠', label: 'AI 分析', color: 'bg-status-info/15 text-status-info', animate: true },
  storing:              { icon: '💾', label: '存储中', color: 'bg-status-info/15 text-status-info', animate: true },
  completed:            { icon: '✅', label: '已完成', color: 'bg-status-success/15 text-status-success' },
  failed:               { icon: '❌', label: '失败', color: 'bg-status-error/15 text-status-error' },
  cancelled:            { icon: '⏹️', label: '已取消', color: 'bg-gray-500/15 text-gray-500' },
};

/**
 * 获取分析状态的显示配置
 */
export function getAnalysisStatusConfig(status: string): AnalysisStatusConfig {
  return ANALYSIS_STATUS_CONFIG[status] ?? ANALYSIS_STATUS_CONFIG.pending;
}

/**
 * 文件类型图标映射
 */
export const FILE_ICONS: Record<string, string> = {
  '.py': '🐍',
  '.js': '⚡',
  '.ts': '📘',
  '.tsx': '⚛️',
  '.jsx': '⚛️',
  '.java': '☕',
  '.go': '🔵',
  '.rs': '🦘',
  '.cpp': '🔶',
  '.cc': '🔶',
  '.cxx': '🔶',
  '.h': '🔷',
  '.hpp': '🔷',
  '.c': '🔶',
  '.cs': '🛵',
  '.rb': '💎',
  '.php': '💫',
  '.swift': '🐘',
  '.kt': '🧴',
  '.css': '🎨',
  '.scss': '🎨',
  '.json': '📋',
  '.yaml': '📋',
  '.yml': '📋',
  '.toml': '📋',
  '.xml': '📋',
  '.md': '📝',
  '.txt': '📄',
  '.sh': '💻',
  '.sql': '🗃️',
  default: '📄',
};

/**
 * 获取文件图标
 */
export function getFileIcon(filename: string): string {
  const ext = filename.slice(filename.lastIndexOf('.'));
  return FILE_ICONS[ext] ?? FILE_ICONS.default;
}
