"use client";

import { use, useState, useMemo, useCallback, useEffect, useRef } from "react";
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
import { NavTrailBar } from "@/components/analysis/NavTrailBar";
import type { NavEntry } from "@/components/analysis/NavTrailBar";

export type TabType =
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
  const [selectedFilePath, setSelectedFilePath] = useState<string>("");
  const [activeTab, setActiveTab] = useState<TabType>("structure");
  const [highlightNodeId, setHighlightNodeId] = useState<string | null>(null);

  // 探索轨迹栈（Photoshop 式历史记录）
  const [navStack, setNavStack] = useState<NavEntry[]>([]);
  const [navIndex, setNavIndex] = useState(-1);
  const MAX_STACK_DEPTH = 20;

  const handleNavigate = useCallback(
    (entry: Omit<NavEntry, "component"> & { component?: TabType }) => {
      const targetFileId = entry.fileId ?? selectedFileId ?? null;

      const newEntry: NavEntry = {
        component: entry.component ?? activeTab,
        fileId: targetFileId,
        nodeId: entry.nodeId ?? null,
        label: entry.label,
        detail: entry.detail,
      };

      const currentEntry: NavEntry = {
        component: activeTab,
        fileId: selectedFileId ?? null,
        nodeId: null,
        label: selectedFileName,
        detail: "",
      };

      setNavStack((prev) => {
        let base = prev;
        if (navIndex >= 0 && navIndex < prev.length - 1) {
          base = prev.slice(0, navIndex + 1);
        }

        const stackTop = base[base.length - 1];
        const sameFileAsStackTop =
          !!stackTop &&
          !!targetFileId &&
          stackTop.fileId === targetFileId;

        let result: NavEntry[];
        if (sameFileAsStackTop) {
          result = [...base.slice(0, -1), newEntry];
        } else {
          const duplicatesStackTop =
            !!stackTop &&
            stackTop.component === currentEntry.component &&
            stackTop.fileId === currentEntry.fileId;

          if (duplicatesStackTop) {
            result = [...base, newEntry];
          } else {
            result = [...base, currentEntry, newEntry];
          }
        }

        if (result.length > MAX_STACK_DEPTH) {
          result = result.slice(-MAX_STACK_DEPTH);
        }

        setNavIndex(result.length - 1);
        return result;
      });

      if (entry.component) {
        setActiveTab(entry.component);
      }
      if (entry.fileId) {
        setSelectedFileId(entry.fileId);
        const currentFiles = filesRef.current;
        if (currentFiles && entry.fileId) {
          const found = currentFiles.find(f => f.id === entry.fileId);
          if (found) {
            setSelectedFilePath(found.path);
            setSelectedFileName(found.path.split("/").pop() ?? found.path);
          } else {
            setSelectedFileName(entry.label);
          }
        } else {
          setSelectedFileName(entry.label);
        }
      }
      if (entry.nodeId) {
        setHighlightNodeId(entry.nodeId);
      } else {
        setHighlightNodeId(null);
      }
    },
    [activeTab, selectedFileId, selectedFileName, navIndex]
  );

  const handleNavigateBack = useCallback(() => {
    setNavStack((prev) => {
      if (prev.length <= 1 || navIndex <= 0) {
        setHighlightNodeId(null);
        setNavIndex(-1);
        return prev.length <= 1 ? [] : prev;
      }
      const newIndex = navIndex - 1;
      setNavIndex(newIndex);
      const prevEntry = prev[newIndex];
      setActiveTab(prevEntry.component);
      if (prevEntry.fileId) {
        setSelectedFileId(prevEntry.fileId);
        setSelectedFileName(prevEntry.label);
      }
      setHighlightNodeId(prevEntry.nodeId ?? null);
      return prev;
    });
  }, [navIndex]);

  const handleClearNavStack = useCallback(() => {
    setNavStack([]);
    setNavIndex(-1);
    setHighlightNodeId(null);
  }, []);

  const handleJumpTo = useCallback((index: number) => {
    setNavStack((prev) => {
      if (index < 0 || index >= prev.length) return prev;
      const target = prev[index];
      setActiveTab(target.component);
      if (target.fileId) {
        setSelectedFileId(target.fileId);
        setSelectedFileName(target.label);
      }
      setHighlightNodeId(target.nodeId ?? null);
      setNavIndex(index);
      return prev;
    });
  }, []);

  // 键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && e.key === "ArrowLeft") {
        e.preventDefault();
        handleNavigateBack();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleNavigateBack]);

  const { data: files, isLoading, error } = useFiles(repo_id);
  const filesRef = useRef(files);
  filesRef.current = files;

  useEffect(() => {
    if (selectedFileId && files) {
      const found = files.find(f => f.id === selectedFileId);
      if (found && found.path !== selectedFilePath) {
        setSelectedFilePath(found.path);
      }
    }
  }, [selectedFileId, files, selectedFilePath]);

  const tree = useMemo(() => buildFileTree(files ?? []), [files]);
  const fileCount = useMemo(() => countFiles(tree), [tree]);

  const handleSelectFile = (fileId: string, filePath: string) => {
    setSelectedFileId(fileId);
    setSelectedFilePath(filePath);
    const name = filePath.split("/").pop() ?? filePath;
    setSelectedFileName(name);
  };

  return (
    <div className="flex flex-col gap-4 h-[calc(100vh-120px)]">
      {/* 探索轨迹栏 */}
      <NavTrailBar
        stack={navStack}
        activeIndex={navIndex}
        onBack={handleNavigateBack}
        onClear={handleClearNavStack}
        onJumpTo={handleJumpTo}
      />

      {/* 主内容区 */}
      <div className="flex gap-6 flex-1 min-h-0">
        {/* 左侧：文件树 — 磨砂玻璃面板 */}
        <div className="w-1/2 max-w-md flex flex-col bg-[var(--bg-card)]/60 backdrop-blur-sm rounded-xl border border-white/[0.06] overflow-hidden">
          <div className="border-b border-white/[0.06] px-4 py-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              {"文件树"}
            </h2>
            <span className="text-xs text-[var(--text-muted)] font-mono tabular-nums">
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
              <div className="text-center text-status-error text-sm py-4">
                {"加载文件列表失败"}
              </div>
            ) : (
              <FileTree
                nodes={tree}
                selectedFileId={selectedFileId ?? undefined}
                selectedFilePath={selectedFilePath}
                onSelectFile={handleSelectFile}
                onNavigate={handleNavigate}
              />
            )}
          </div>
        </div>

        {/* 右侧：标签页内容 — 磨砂玻璃面板 */}
        <div className="flex-1 flex flex-col bg-[var(--bg-card)]/60 backdrop-blur-sm rounded-xl border border-white/[0.06] overflow-hidden relative">
          {/* 标签页头部 — 无分隔线，单个 pill 激活态 */}
          <div className="flex flex-wrap gap-0.5 px-3 pt-3 pb-2 border-b border-white/[0.06]">
            <TabButton label="项目概览" active={activeTab === "overview"} onClick={() => setActiveTab("overview")} />
            <TabButton label="代码结构" active={activeTab === "structure"} onClick={() => setActiveTab("structure")} />
            <TabButton label="调用图" active={activeTab === "callgraph"} onClick={() => setActiveTab("callgraph")} />
            <TabButton label="API 路由" active={activeTab === "routes"} onClick={() => setActiveTab("routes")} />
            <TabButton label="外部依赖" active={activeTab === "dependencies"} onClick={() => setActiveTab("dependencies")} />
            <TabButton label="模块依赖" active={activeTab === "module-deps"} onClick={() => setActiveTab("module-deps")} />
            <TabButton label="框架检测" active={activeTab === "frameworks"} onClick={() => setActiveTab("frameworks")} />
            <TabButton label="版本管理" active={activeTab === "versions"} onClick={() => setActiveTab("versions")} />
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
                <StructureList
                  fileId={selectedFileId!}
                  fileName={selectedFileName}
                  onNavigate={handleNavigate}
                  highlightNodeId={highlightNodeId ?? undefined}
                />
              </div>
            ) : activeTab === "callgraph" ? (
              <CallGraph
                fileId={selectedFileId!}
                repositoryId={repo_id}
                onNavigate={handleNavigate}
                highlightNodeId={highlightNodeId ?? undefined}
              />
            ) : activeTab === "routes" ? (
              <div className="h-full overflow-y-auto p-4">
                <RouteList repositoryId={repo_id} onNavigate={handleNavigate} />
              </div>
            ) : activeTab === "dependencies" ? (
              <div className="h-full overflow-y-auto p-4">
                <DependencyList repositoryId={repo_id} />
              </div>
            ) : activeTab === "module-deps" ? (
              <div className="h-full overflow-y-auto p-4">
                <ModuleDependencyGraph
                  repositoryId={repo_id}
                  onNavigate={handleNavigate}
                />
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
      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
        active
          ? "bg-brand/10 text-brand shadow-sm"
          : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
      }`}
    >
      {label}
    </button>
  );
}