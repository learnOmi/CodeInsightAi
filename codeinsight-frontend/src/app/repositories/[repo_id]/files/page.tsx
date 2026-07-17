"use client";

import { use, useState, useMemo } from "react";
import { useFiles } from "@/hooks/use-files";
import { buildFileTree, countFiles } from "@/utils/tree-utils";
import { FileTree } from "@/components/file-tree";
import { StructureList } from "@/components/structure";
import { CallGraph } from "@/components/call-graph";
import { VersionManager } from "@/components/VersionManager";
import { RouteList } from "@/components/analysis/RouteList";
import { DependencyList } from "@/components/analysis/DependencyList";
import { FrameworkList } from "@/components/analysis/FrameworkList";

type TabType =
  | "structure"
  | "callgraph"
  | "versions"
  | "routes"
  | "dependencies"
  | "frameworks";

/** 需要选中文件的 Tab */
const FILE_DEPENDENT_TABS: TabType[] = ["structure", "callgraph"];

/** 文件树 + 结构概览页面 */
export default function FilesPage({
  params,
}: {
  params: Promise<{ repo_id: string }>;
}) {
  const { repo_id } = use(params);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string>("");
  const [activeTab, setActiveTab] = useState<TabType>("structure");

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

      {/* 右侧：标签页内容 */}
      <div className="flex-1 bg-[var(--bg-card)] rounded-lg border border-[var(--border)] overflow-hidden flex flex-col">
        {/* 标签页头部 */}
        <div className="border-b border-[var(--border)] flex flex-wrap">
          <button
            onClick={() => setActiveTab("structure")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-r border-[var(--border)] last:border-r-0 ${
              activeTab === "structure"
                ? "bg-[var(--bg-primary)] text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
            }`}
          >
            {"代码结构"}
          </button>
          <button
            onClick={() => setActiveTab("callgraph")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-r border-[var(--border)] last:border-r-0 ${
              activeTab === "callgraph"
                ? "bg-[var(--bg-primary)] text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
            }`}
          >
            {"调用图"}
          </button>
          <button
            onClick={() => setActiveTab("routes")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-r border-[var(--border)] last:border-r-0 ${
              activeTab === "routes"
                ? "bg-[var(--bg-primary)] text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
            }`}
          >
            {"API 路由"}
          </button>
          <button
            onClick={() => setActiveTab("dependencies")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-r border-[var(--border)] last:border-r-0 ${
              activeTab === "dependencies"
                ? "bg-[var(--bg-primary)] text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
            }`}
          >
            {"外部依赖"}
          </button>
          <button
            onClick={() => setActiveTab("frameworks")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-r border-[var(--border)] last:border-r-0 ${
              activeTab === "frameworks"
                ? "bg-[var(--bg-primary)] text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
            }`}
          >
            {"框架检测"}
          </button>
          <button
            onClick={() => setActiveTab("versions")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-r border-[var(--border)] last:border-r-0 ${
              activeTab === "versions"
                ? "bg-[var(--bg-primary)] text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
            }`}
          >
            {"版本管理"}
          </button>
        </div>

        {/* 标签页内容 */}
        <div className="flex-1 overflow-hidden">
          {FILE_DEPENDENT_TABS.includes(activeTab) && !selectedFileId ? (
            <div className="h-full flex items-center justify-center text-[var(--text-muted)] text-sm">
              {"请从左侧文件树中选择一个文件"}
            </div>
          ) : activeTab === "structure" ? (
            <div className="h-full overflow-y-auto p-4">
              <StructureList fileId={selectedFileId!} fileName={selectedFileName} />
            </div>
          ) : activeTab === "callgraph" ? (
            <CallGraph fileId={selectedFileId!} repositoryId={repo_id} />
          ) : activeTab === "routes" ? (
            <div className="h-full overflow-y-auto p-4">
              <RouteList repositoryId={repo_id} />
            </div>
          ) : activeTab === "dependencies" ? (
            <div className="h-full overflow-y-auto p-4">
              <DependencyList repositoryId={repo_id} />
            </div>
          ) : activeTab === "frameworks" ? (
            <div className="h-full overflow-y-auto p-4">
              <FrameworkList repositoryId={repo_id} />
            </div>
          ) : (
            <div className="h-full overflow-y-auto p-4">
              <VersionManager repositoryId={repo_id} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
