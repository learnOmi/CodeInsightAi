import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getRepositories,
  getRepository,
  createRepository,
  updateRepository,
  deleteRepository,
  submitAnalysis,
  getTaskStatus,
  cancelTask,
  getVersions,
  switchVersion,
  rollbackVersion,
} from "@/api/repositories";
import { APIError } from "@/api/base";
import type { components } from "@codeinsight/shared";

type RepositoryCreate = components["schemas"]["RepositoryCreate"];
type RepositoryUpdate = components["schemas"]["RepositoryUpdate"];
type AnalyzeRequest = components["schemas"]["AnalyzeRequest"];
type AnalysisTask = components["schemas"]["AnalysisTask"];
type AnalysisVersion = components["schemas"]["AnalysisVersion"];

export function useRepositories() {
  return useQuery({
    queryKey: ["repositories"],
    queryFn: getRepositories,
  });
}

export function useRepository(id: string) {
  return useQuery({
    queryKey: ["repositories", id],
    queryFn: () => getRepository(id),
    enabled: !!id,
  });
}

export function useCreateRepository() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: RepositoryCreate) => createRepository(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useUpdateRepository() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: RepositoryUpdate }) =>
      updateRepository(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["repositories", id] });
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useDeleteRepository() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteRepository(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useSubmitAnalysis() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ repositoryId, data }: { repositoryId: string; data?: AnalyzeRequest }) =>
      submitAnalysis(repositoryId, data),
    onSuccess: (_, { repositoryId }) => {
      queryClient.invalidateQueries({ queryKey: ["repositories", repositoryId] });
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useTaskStatus(taskId: string, enabled = true) {
  return useQuery<AnalysisTask>({
    queryKey: ["tasks", taskId],
    queryFn: () => getTaskStatus(taskId),
    enabled: !!taskId && enabled,
    refetchInterval: (query) => {
      // Stop polling on 401 (token expired)
      if (query.state.error instanceof APIError && query.state.error.status === 401) {
        return false;
      }
      // Stop polling when task is completed/failed/cancelled
      if (query.state.data && ["completed", "failed", "cancelled"].includes(query.state.data.status)) {
        return false;
      }
      return 2000;
    },
  });
}

export function useCancelTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (taskId: string) => cancelTask(taskId),
    onSuccess: (_, taskId) => {
      queryClient.invalidateQueries({ queryKey: ["tasks", taskId] });
    },
  });
}

export function useVersions(repositoryId: string) {
  return useQuery<AnalysisVersion[]>({
    queryKey: ["repositories", repositoryId, "versions"],
    queryFn: () => getVersions(repositoryId),
    enabled: !!repositoryId,
  });
}

export function useSwitchVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ repositoryId, version }: { repositoryId: string; version: string }) =>
      switchVersion(repositoryId, version),
    onSuccess: (_, { repositoryId }) => {
      queryClient.invalidateQueries({ queryKey: ["repositories", repositoryId] });
      queryClient.invalidateQueries({ queryKey: ["repositories", repositoryId, "versions"] });
    },
  });
}

export function useRollbackVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ repositoryId, version }: { repositoryId: string; version: string }) =>
      rollbackVersion(repositoryId, version),
    onSuccess: (_, { repositoryId }) => {
      queryClient.invalidateQueries({ queryKey: ["repositories", repositoryId] });
      queryClient.invalidateQueries({ queryKey: ["repositories", repositoryId, "versions"] });
    },
  });
}