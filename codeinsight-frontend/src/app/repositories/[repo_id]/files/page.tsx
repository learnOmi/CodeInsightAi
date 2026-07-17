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
import { RepositoryOverview } from "@/components/analysis/RepositoryOverview";
import { ModuleDependencyGraph } from "@/components/analysis/ModuleDependencyGraph";

type TabType =
  | "overview"
  | "structure"
  | "callgraph"
  | "versions"
  | "routes"
  | "dependencies"
  | "frameworks"
  | "module-deps";

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
          <TabButton
            label="项目概览"
            active={activeTab === "overview"}
            onClick={() => setActiveTab("overview")}
          />
          <TabButton
            label="代码结构"
            active={activeTab === "structure"}
            onClick={() => setActiveTab("structure")}
          />
          <TabButton
            label="调用图"
            active={activeTab === "callgraph"}
            onClick={() => setActiveTab("callgraph")}
          />
          <TabButton
            label="API 路由"
            active={activeTab === "routes"}
            onClick={() => setActiveTab("routes")}
          />
          <TabButton
            label="外部依赖"
            active={activeTab === "dependencies"}
            onClick={() => setActiveTab("dependencies")}
          />
          <TabButton
            label="模块依赖"
            active={activeTab === "module-deps"}
            onClick={() => setActiveTab("module-deps")}
          />
          <TabButton
            label="框架检测"
            active={activeTab === "frameworks"}
            onClick={() => setActiveTab("frameworks")}
          />
          <TabButton
            label="版本管理"
            active={activeTab === "versions"}
            onClick={() => setActiveTab("versions")}
          />
        </div>

        {/* 标签页内容 */}
        <div className="flex-1 overflow-hidden">
          {FILE_DEPENDENT_TABS.includes(activeTab) && !selectedFileId ? (
            <div className="h-full flex items-center justify-center text-[var(--text-muted)] text-sm">
              {"请从左侧文件树中选择一个文件"}
            </div>
          ) : activeTab === "overview" ? (
            <div className="h-full overflow-y-auto p-4">
              <RepositoryOverview repositoryId={repo_id} />
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
          ) : activeTab === "module-deps" ? (
            <div className="h-full overflow-y-auto p-4">
              <ModuleDependencyGraph repositoryId={repo_id} />
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

function TabButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium transition-colors border-r border-[var(--border)] last:border-r-0 ${
        active
          ? "bg-[var(--bg-primary)] text-[var(--text-primary)]"
          : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
      }`}
    >
      {label}
    </button>
  );
}
