/**
 * 仓库相关类型定义
 */

/**
 * 仓库状态枚举
 */
export enum RepositoryStatus {
  PENDING = 'pending',
  ANALYZING = 'analyzing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

/**
 * 仓库信息
 */
export interface Repository {
  /** 仓库唯一 ID */
  id: string;
  /** 仓库名称 */
  name: string;
  /** 本地代码仓库路径 */
  path: string;
  /** 当前分析状态 */
  status: RepositoryStatus;
  /** 当前分析版本号 */
  currentVersion: string | null;
  /** 代码文件总数 */
  fileCount: number;
  /** 代码总行数 */
  lineCount: number;
  /** 知识点总数 */
  knowledgePointsCount: number;
  /** 语言分布 */
  languageDistribution: Record<string, number>;
  /** 创建时间 */
  createdAt: string;
  /** 最后更新时间 */
  updatedAt: string;
  /** 最后分析时间 */
  lastAnalyzedAt: string | null;
}

/**
 * 创建仓库请求
 */
export interface RepositoryCreate {
  /** 仓库名称，长度 1-100 */
  name: string;
  /** 本地代码仓库绝对路径 */
  path: string;
  /** 添加后立即开始分析，默认 true */
  autoAnalyze?: boolean;
}

/**
 * 更新仓库请求
 */
export interface RepositoryUpdate {
  /** 新名称 */
  name?: string;
}
