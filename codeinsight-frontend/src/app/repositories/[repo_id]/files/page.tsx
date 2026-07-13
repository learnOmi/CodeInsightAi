"use client";

import { use, useState, useMemo } from "react";
import { useFiles } from "@/hooks/use-files";
import { buildFileTree, countFiles } from "@/utils/tree-utils";
import { FileTree } from "@/components/file-tree";
import { StructureList } from "@/components/structure";

/** 文件树 + 结构概览页面 */
export default function FilesPage({
  params,
}: {
  params: Promise<{ repo_id: string }>;
}) {
  const { repo_id } = use(params);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string>("");

  const { data: files, isLoading, error } = useFiles(repo_id);

  const tree = useMemo(() => buildFileTree(files ?? []), [files]);
  const fileCount = useMemo(() => countFiles(tree), [tree]);

  const handleSelectFile = (fileId: string, filePath: string) => {
    setSelectedFileId(fileId);
    const name = filePath.split("/").pop() ?? filePath;
    setSelectedFileName(name);
  };

  return (
    <div className="flex gap-6 h-[calc(100vh-120px)]">
      {/* 左侧：文件树 */}
      <div className="w-1/2 max-w-md flex flex-col bg-[var(--bg-card)] rounded-lg border border-[var(--border)] overflow-hidden">
        <div className="border-b border-[var(--border)] px-4 py-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            {"文件树"}
          </h2>
          <span className="text-xs text-[var(--text-muted)]">
            {fileCount} {"个文件"}
          </span>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(10)].map((_, i) => (
                <div
                  key={i}
                  className="h-6 bg-[var(--bg-hover)] rounded animate-pulse"
                  style={{ width: `${80 - (i % 5) * 10}%`, marginLeft: `${(i % 3) * 16}px` }}
                />
              ))}
            </div>
          ) : error ? (
            <div className="text-center text-red-500 text-sm py-4">
              {"加载文件列表失败"}
            </div>
          ) : (
            <FileTree
              nodes={tree}
              selectedFileId={selectedFileId ?? undefined}
              onSelectFile={handleSelectFile}
            />
          )}
        </div>
      </div>

      {/* 右侧：结构概览 */}
      <div className="flex-1 bg-[var(--bg-card)] rounded-lg border border-[var(--border)] overflow-hidden">
        <div className="border-b border-[var(--border)] px-4 py-3">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            {"代码结构"}
          </h2>
        </div>
        <div className="overflow-y-auto p-4">
          {selectedFileId ? (
            <StructureList fileId={selectedFileId} fileName={selectedFileName} />
          ) : (
            <div className="text-center text-[var(--text-muted)] text-sm py-12">
              {"请从左侧文件树中选择一个文件"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
