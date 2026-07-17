import { useQuery } from "@tanstack/react-query";
import {
  getDependencies,
  getDependenciesCount,
  type ExternalDependency,
} from "@/api/dependencies";
import { getRoutes, getRoutesCount, type ApiRoute } from "@/api/routes";
import {
  getFrameworks,
  getFrameworksCount,
  type FrameworkPattern,
} from "@/api/frameworks";
import {
  getRepositoryStats,
  type RepositoryStats,
} from "@/api/stats";
import {
  getModuleDependencies,
  getModuleDependenciesCount,
  getModuleDependencyStats,
  type ModuleDependency,
  type ModuleDependencyStats,
} from "@/api/module-dependencies";

// ===== 外部依赖 =====

/** 外部依赖列表 */
export function useDependencies(
  repositoryId: string,
  params?: { ecosystem?: string; scope?: string }
) {
  return useQuery({
    queryKey: ["dependencies", repositoryId, params],
    queryFn: () => getDependencies(repositoryId, params),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

/** 外部依赖数量 */
export function useDependenciesCount(repositoryId: string) {
  return useQuery({
    queryKey: ["dependencies-count", repositoryId],
    queryFn: () => getDependenciesCount(repositoryId),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

// ===== API 路由 =====

/** API 路由列表 */
export function useRoutes(
  repositoryId: string,
  params?: { httpMethod?: string; framework?: string; pathPattern?: string }
) {
  return useQuery({
    queryKey: ["routes", repositoryId, params],
    queryFn: () => getRoutes(repositoryId, params),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

/** API 路由数量 */
export function useRoutesCount(repositoryId: string) {
  return useQuery({
    queryKey: ["routes-count", repositoryId],
    queryFn: () => getRoutesCount(repositoryId),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

// ===== 框架检测 =====

/** 框架检测结果 */
export function useFrameworks(
  repositoryId: string,
  params?: { category?: string; minConfidence?: number }
) {
  return useQuery({
    queryKey: ["frameworks", repositoryId, params],
    queryFn: () => getFrameworks(repositoryId, params),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

/** 框架检测数量 */
export function useFrameworksCount(repositoryId: string) {
  return useQuery({
    queryKey: ["frameworks-count", repositoryId],
    queryFn: () => getFrameworksCount(repositoryId),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

// ===== 项目统计 =====

/** 仓库全局统计 */
export function useRepositoryStats(repositoryId: string) {
  return useQuery({
    queryKey: ["repository-stats", repositoryId],
    queryFn: () => getRepositoryStats(repositoryId),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

// ===== 模块依赖 =====

/** 模块依赖列表 */
export function useModuleDependencies(repositoryId: string) {
  return useQuery({
    queryKey: ["module-dependencies", repositoryId],
    queryFn: () => getModuleDependencies(repositoryId),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

/** 模块依赖数量 */
export function useModuleDependenciesCount(repositoryId: string) {
  return useQuery({
    queryKey: ["module-dependencies-count", repositoryId],
    queryFn: () => getModuleDependenciesCount(repositoryId),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

/** 模块依赖统计 */
export function useModuleDependencyStats(repositoryId: string) {
  return useQuery({
    queryKey: ["module-dependency-stats", repositoryId],
    queryFn: () => getModuleDependencyStats(repositoryId),
    enabled: !!repositoryId,
    staleTime: 2 * 60 * 1000,
  });
}

// 类型导出
export type { ExternalDependency, ApiRoute, FrameworkPattern, RepositoryStats, ModuleDependency, ModuleDependencyStats };
