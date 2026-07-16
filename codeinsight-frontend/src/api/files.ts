import { apiFetch } from "./base";
import type { components } from "@codeinsight/shared";

type FileItem = components["schemas"]["File"];
export type { FileItem };

/** 分页响应类型 */
export interface FilesPageResponse {
  items: FileItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** 获取文件列表（分页） */
export async function getFiles(
  repositoryId: string,
  page: number = 1,
  pageSize: number = 100
): Promise<FilesPageResponse> {
  const params = new URLSearchParams({
    repository_id: repositoryId,
    page: String(page),
    page_size: String(pageSize),
  });
  return apiFetch<FilesPageResponse>(`/api/v1/files?${params.toString()}`);
}

/** 获取所有文件（自动分页加载全部） */
export async function getAllFiles(repositoryId: string): Promise<FileItem[]> {
  const pageSize = 500;
  const firstPage = await getFiles(repositoryId, 1, pageSize);
  if (firstPage.total_pages <= 1) {
    return firstPage.items;
  }

  const allItems = [...firstPage.items];
  for (let p = 2; p <= firstPage.total_pages; p++) {
    const page = await getFiles(repositoryId, p, pageSize);
    allItems.push(...page.items);
  }
  return allItems;
}

/** 获取单个文件 */
export async function getFile(fileId: string): Promise<FileItem> {
  return apiFetch(`/api/v1/files/${fileId}`);
}
