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
