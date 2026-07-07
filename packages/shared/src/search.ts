/**
 * 搜索相关类型定义
 */

/**
 * 搜索模式
 */
export enum SearchMode {
  /** 全文搜索（Meilisearch） */
  TEXT = 'text',
  /** 向量语义搜索（pgvector） */
  VECTOR = 'vector',
  /** 混合搜索（加权合并） */
  HYBRID = 'hybrid',
}

/**
 * 搜索结果类型
 */
export enum SearchResultType {
  KNOWLEDGE_POINT = 'knowledge_point',
  REPOSITORY = 'repository',
  FILE = 'file',
}

/**
 * 搜索请求参数
 */
export interface SearchRequest {
  /** 搜索关键词 */
  q: string;
  /** 限定仓库 ID，不传则搜索所有 */
  repositoryId?: string;
  /** 按分类筛选 */
  category?: string;
  /** 搜索模式 */
  mode?: SearchMode;
  /** 页码，默认 1 */
  page?: number;
  /** 每页数量，默认 20 */
  pageSize?: number;
}

/**
 * 搜索结果
 */
export interface SearchResult {
  /** 结果类型 */
  type: SearchResultType;
  /** 相关性分数 (0-1) */
  score: number;
  /** 匹配的知识点 ID */
  pointId?: string;
  /** 匹配的知识点摘要 */
  point?: {
    id: string;
    title: string;
    category: string;
    description: string;
    repositoryId: string;
    repositoryName: string;
    version: string;
  };
  /** 匹配的仓库信息 */
  repository?: {
    id: string;
    name: string;
    path: string;
    status: string;
  };
  /** 命中的文本片段 */
  matchedText?: string;
}

/**
 * 搜索响应
 */
export interface SearchResponse {
  /** 原始查询词 */
  query: string;
  /** 使用的搜索模式 */
  mode: SearchMode;
  /** 搜索结果列表 */
  results: SearchResult[];
  /** 分类 Facet 统计 */
  facets?: {
    byCategory: Record<string, number>;
    byRepository: Record<string, number>;
  };
  /** 搜索耗时（毫秒） */
  durationMs: number;
}

/**
 * 搜索建议
 */
export interface SearchSuggestion {
  /** 建议文本 */
  text: string;
  /** 建议类型 */
  type: string;
  /** 出现次数 */
  count: number;
}

/**
 * 搜索建议响应
 */
export interface SearchSuggestionsResponse {
  /** 原始查询词 */
  query: string;
  /** 建议列表 */
  suggestions: SearchSuggestion[];
}
