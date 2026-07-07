/**
 * 知识点相关类型定义
 */

/**
 * 知识点分类枚举
 * 
 * DP-: 设计模式 (Design Pattern)
 * AD-: 架构决策 (Architecture Decision)
 * AL-: 算法实现 (Algorithm)
 * ET-: 工程技巧 (Engineering Tip)
 * DK-: 领域知识 (Domain Knowledge)
 */
export enum KnowledgeCategory {
  DESIGN_PATTERN = 'DP-',
  ARCHITECTURE_DECISION = 'AD-',
  ALGORITHM = 'AL-',
  ENGINEERING_TIP = 'ET-',
  DOMAIN_KNOWLEDGE = 'DK-',
}

/**
 * 知识点分类名称映射
 */
export const KNOWLEDGE_CATEGORY_NAMES: Record<KnowledgeCategory, string> = {
  [KnowledgeCategory.DESIGN_PATTERN]: '设计模式',
  [KnowledgeCategory.ARCHITECTURE_DECISION]: '架构决策',
  [KnowledgeCategory.ALGORITHM]: '算法实现',
  [KnowledgeCategory.ENGINEERING_TIP]: '工程技巧',
  [KnowledgeCategory.DOMAIN_KNOWLEDGE]: '领域知识',
};

/**
 * 代码片段
 */
export interface CodeSnippet {
  /** 文件相对路径 */
  filePath: string;
  /** 起始行号（从 1 开始） */
  startLine: number;
  /** 结束行号（从 1 开始） */
  endLine: number;
  /** 需要高亮的行号列表 */
  highlightedLines: number[];
  /** 编程语言 */
  language: string;
  /** 代码签名（函数/类名） */
  signature: string;
}

/**
 * 调用链节点
 */
export interface CallChainNode {
  /** 节点唯一 ID */
  nodeId: string;
  /** 节点类型 */
  nodeType: 'function' | 'class' | 'method' | 'function_call' | 'import' | 'module';
  /** 文件路径 */
  file: string;
  /** 行号范围 [start, end] */
  lines: [number, number];
  /** 代码签名 */
  signature: string;
  /** 链路方向：entry(入口) / call(调用) / implementation(实现) / export(导出) */
  direction: 'entry' | 'call' | 'implementation' | 'export';
}

/**
 * 拓展内容
 */
export interface ExpansionContent {
  /** 原理分析 */
  principle: string;
  /** 适用场景列表 */
  applicableScenarios: string[];
  /** 最佳实践列表 */
  bestPractices: string[];
  /** 相关知识点/模式列表 */
  relatedPatterns: string[];
  /** 学习资料链接列表 */
  learningResources: LearningResource[];
}

/**
 * 学习资料
 */
export interface LearningResource {
  /** 标题 */
  title: string;
  /** 链接 URL */
  url: string;
  /** 类型：book / article / video / course */
  type: 'book' | 'article' | 'video' | 'course';
}

/**
 * 知识点元数据
 */
export interface KnowledgeMetadata {
  /** 负责分析的 Agent 名称 */
  agent: string;
  /** Prompt 版本号 */
  promptVersion: string;
  /** 使用的 LLM 模型 */
  model: string;
  /** Token 消耗统计 */
  tokensUsed: {
    input: number;
    output: number;
  };
}

/**
 * 知识点
 */
export interface KnowledgePoint {
  /** 知识点唯一 ID */
  id: string;
  /** 所属分类 */
  category: KnowledgeCategory;
  /** 分类显示名称 */
  categoryName: string;
  /** 标题 */
  title: string;
  /** 描述 */
  description: string;
  /** 置信度 (0-1) */
  confidence: number;
  /** 标签列表 */
  tags: string[];
  /** 关联代码片段 */
  codeSnippets: CodeSnippet[];
  /** 调用链 */
  callChain: CallChainNode[];
  /** AI 生成的拓展内容 */
  expansion: ExpansionContent;
  /** 分析版本号 */
  version: string;
  /** 所属仓库 ID */
  repositoryId: string;
  /** 元数据 */
  metadata: KnowledgeMetadata;
  /** 创建时间 */
  createdAt: string;
  /** 最后更新时间 */
  updatedAt: string;
}

/**
 * 知识点统计
 */
export interface KnowledgeStats {
  /** 知识点总数 */
  totalPoints: number;
  /** 按分类统计 */
  byCategory: Record<KnowledgeCategory, number>;
  /** 按置信度统计 */
  byConfidence: {
    high: number;    // >= 0.8
    medium: number;  // 0.5 - 0.8
    low: number;     // < 0.5
  };
  /** 热门标签 Top N */
  topTags: Array<{ tag: string; count: number }>;
  /** 覆盖文件数 */
  filesCovered: number;
  /** 分析总行数 */
  totalLinesAnalyzed: number;
}
