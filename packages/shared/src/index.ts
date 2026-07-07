/**
 * CodeInsight AI 共享类型与常量
 *
 * 架构说明：
 * - 类型定义：由后端 Pydantic Schema 通过 OpenAPI 自动生成（generated.ts）
 * - 常量定义：前端专属的显示映射等（constants.ts）
 *
 * 类型同步方式：
 *   1. 后端修改 Pydantic Schema
 *   2. 运行 `cd codeinsight-backend && uv run python scripts/export_openapi.py`
 *   3. 运行 `npx openapi-typescript packages/shared/src/openapi.json -o packages/shared/src/generated.ts`
 *   或一键运行：`npm run gen:types`
 */

// 自动生成的类型（从后端 OpenAPI schema）
export type { paths, components, operations } from './generated';

// 前端专属常量
export { KNOWLEDGE_CATEGORY_NAMES, KNOWLEDGE_CATEGORY_COLORS } from './constants';
