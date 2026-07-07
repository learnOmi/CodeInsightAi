/**
 * 分析任务相关类型定义
 */

/**
 * 分析模式
 */
export enum AnalysisMode {
  FULL = 'full',
  INCREMENTAL = 'incremental',
}

/**
 * 分析任务状态
 */
export enum TaskStatus {
  PENDING = 'pending',
  SCANNING = 'scanning',
  PARSING = 'parsing',
  ANALYZING_MODULES = 'analyzing_modules',
  STORING = 'storing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

/**
 * 启用的 Agent 类型
 */
export type AgentType =
  | 'design_pattern'
  | 'architecture'
  | 'algorithm'
  | 'engineering_tips'
  | 'domain_knowledge';

/**
 * 分析进度信息
 */
export interface AnalysisProgress {
  /** 当前步骤 */
  currentStep: TaskStatus;
  /** 完成百分比 (0-100) */
  percent: number;
  /** 已处理文件数 */
  filesProcessed: number;
  /** 文件总数 */
  filesTotal: number;
  /** 已发现知识点数 */
  knowledgePointsFound: number;
}

/**
 * 提交分析任务请求
 */
export interface AnalyzeRequest {
  /** 分析模式：full / incremental */
  mode?: AnalysisMode;
  /** 启用的 Agent 列表，默认全部 */
  agents?: AgentType[];
}

/**
 * 分析任务
 */
export interface AnalysisTask {
  /** Celery 任务 ID */
  taskId: string;
  /** 所属仓库 ID */
  repositoryId: string;
  /** 当前状态 */
  status: TaskStatus;
  /** 分析模式 */
  mode: AnalysisMode;
  /** 进度信息 */
  progress: AnalysisProgress;
  /** 提交时间 */
  submittedAt: string;
  /** 开始时间 */
  startedAt: string | null;
  /** 完成时间 */
  completedAt: string | null;
  /** 错误信息（如果失败） */
  errorMessage: string | null;
}

/**
 * 分析版本
 */
export interface AnalysisVersion {
  /** 版本号，格式 v{timestamp}-{short_hash} */
  version: string;
  /** 状态 */
  status: TaskStatus;
  /** 文件总数 */
  totalFiles: number;
  /** 知识点数量 */
  knowledgePointsCount: number;
  /** 是否为当前版本 */
  isCurrent: boolean;
  /** 创建时间 */
  createdAt: string;
  /** 完成时间 */
  completedAt: string | null;
}
