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
  function: { icon: '\u2699\uFE0F', color: 'bg-blue-100 text-blue-700', label: '函数' },
  method: { icon: '\u2699\uFE0F', color: 'bg-blue-100 text-blue-700', label: '方法' },
  class: { icon: '\uD83C\uDFD7\uFE0F', color: 'bg-purple-100 text-purple-700', label: '类' },
  interface: { icon: '\uD83D\uDCC6', color: 'bg-cyan-100 text-cyan-700', label: '接口' },
  module: { icon: '\uD83D\uDCE6', color: 'bg-orange-100 text-orange-700', label: '模块' },
  variable: { icon: '\uD83D\uDCCC', color: 'bg-gray-100 text-gray-700', label: '变量' },
  import: { icon: '\uD83D\uDD17', color: 'bg-green-100 text-green-700', label: '导入' },
  function_call: { icon: '\uD83D\uDCDE', color: 'bg-indigo-100 text-indigo-700', label: '调用' },
  constructor: { icon: '\uD83C\uDFD7\uFE0F', color: 'bg-amber-100 text-amber-700', label: '构造器' },
  default: { icon: '\uD83D\uDCC4', color: 'bg-gray-100 text-gray-600', label: '节点' },
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
  pending: { icon: '\u23F3', label: '待分析', color: 'bg-gray-100 text-gray-600' },
  analyzing: { icon: '\uD83D\uDD04', label: '分析中', color: 'bg-blue-100 text-blue-600', animate: true },
  scanning: { icon: '\uD83D\uDD0D', label: '扫描中', color: 'bg-blue-100 text-blue-600', animate: true },
  parsing: { icon: '\uD83E\uDDE9', label: '解析中', color: 'bg-blue-100 text-blue-600', animate: true },
  analyzing_structures: { icon: '\uD83D\uDCC6', label: '结构分析', color: 'bg-blue-100 text-blue-600', animate: true },
  analyzing_modules: { icon: '\uD83E\uDDE0', label: 'AI 分析', color: 'bg-blue-100 text-blue-600', animate: true },
  storing: { icon: '\uD83D\uDCBE', label: '存储中', color: 'bg-blue-100 text-blue-600', animate: true },
  completed: { icon: '\u2705', label: '已完成', color: 'bg-green-100 text-green-600' },
  failed: { icon: '\u274C', label: '失败', color: 'bg-red-100 text-red-600' },
  cancelled: { icon: '\u23F9\uFE0F', label: '已取消', color: 'bg-gray-100 text-gray-500' },
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
  '.py': '\uD83D\uDC0D',
  '.js': '\u26A1',
  '.ts': '\uD83D\uDCD8',
  '.tsx': '\u269B\uFE0F',
  '.jsx': '\u269B\uFE0F',
  '.java': '\u2615',
  '.go': '\uD83D\uDD35',
  '.rs': '\uD83E\uDD98',
  '.cpp': '\uD83D\uDD36',
  '.cc': '\uD83D\uDD36',
  '.cxx': '\uD83D\uDD36',
  '.h': '\uD83D\uDD37',
  '.hpp': '\uD83D\uDD37',
  '.c': '\uD83D\uDD36',
  '.cs': '\uD83D\uDEF5',
  '.rb': '\uD83D\uDC8E',
  '.php': '\uD83D\uDCAB',
  '.swift': '\uD83D\uDC18',
  '.kt': '\uD83E\uDDF4',
  '.css': '\uD83C\uDFA8',
  '.scss': '\uD83C\uDFA8',
  '.json': '\uD83D\uDCCB',
  '.yaml': '\uD83D\uDCCB',
  '.yml': '\uD83D\uDCCB',
  '.toml': '\uD83D\uDCCB',
  '.xml': '\uD83D\uDCCB',
  '.md': '\uD83D\uDCDD',
  '.txt': '\uD83D\uDCC4',
  '.sh': '\uD83D\uDCBB',
  '.sql': '\uD83D\uDDC3\uFE0F',
  default: '\uD83D\uDCC4',
};

/**
 * 获取文件图标
 */
export function getFileIcon(filename: string): string {
  const ext = filename.slice(filename.lastIndexOf('.'));
  return FILE_ICONS[ext] ?? FILE_ICONS.default;
}
