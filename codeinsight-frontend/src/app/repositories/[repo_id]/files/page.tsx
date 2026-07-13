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
      <div className="w-1/2 max-w-md flex flex-col bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="border-b border-gray-200 px-4 py-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">
            {"\u6587\u4EF6\u6811"}
          </h2>
          <span className="text-xs text-gray-400">
            {fileCount} {"\u4E2A\u6587\u4EF6"}
          </span>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(10)].map((_, i) => (
                <div
                  key={i}
                  className="h-6 bg-gray-100 rounded animate-pulse"
                  style={{ width: `${80 - (i % 5) * 10}%`, marginLeft: `${(i % 3) * 16}px` }}
                />
              ))}
            </div>
          ) : error ? (
            <div className="text-center text-red-500 text-sm py-4">
              {"\u52A0\u8F7D\u6587\u4EF6\u5217\u8868\u5931\u8D25"}
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
      <div className="flex-1 bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="border-b border-gray-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-700">
            {"\u4EE3\u7801\u7ED3\u6784"}
          </h2>
        </div>
        <div className="overflow-y-auto p-4">
          {selectedFileId ? (
            <StructureList fileId={selectedFileId} fileName={selectedFileName} />
          ) : (
            <div className="text-center text-gray-400 text-sm py-12">
              {"\u8BF7\u4ECE\u5DE6\u4FA7\u6587\u4EF6\u6811\u4E2D\u9009\u62E9\u4E00\u4E2A\u6587\u4EF6"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
