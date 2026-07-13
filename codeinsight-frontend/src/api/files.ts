import { apiFetch } from "./base";
import type { components } from "@codeinsight/shared";

type FileItem = components["schemas"]["File"];
export type { FileItem };

/** 获取文件列表（分页） */
export async function getFiles(
  repositoryId: string,
  page: number = 1,
  pageSize: number = 100
): Promise<FileItem[]> {
  const params = new URLSearchParams({
    repository_id: repositoryId,
    page: String(page),
    page_size: String(pageSize),
  });
  return apiFetch(`/api/v1/files?${params.toString()}`);
}

/** 获取单个文件 */
export async function getFile(fileId: string): Promise<FileItem> {
  return apiFetch(`/api/v1/files/${fileId}`);
}
