"use client";

import React from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  FileCode,
  GitBranch,
  Sparkles,
  Tag,
  ExternalLink,
  Code2,
  FileText,
  ArrowRight,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getKnowledgePoint } from "@/api/knowledge";
import { KNOWLEDGE_CATEGORY_COLORS } from "@codeinsight/shared";
import type { components } from "@codeinsight/shared";

type KnowledgePoint = components["schemas"]["KnowledgePoint"];
type ExpansionContent = components["schemas"]["ExpansionContent"];
type CodeSnippet = components["schemas"]["CodeSnippet"];
type CallChainNode = components["schemas"]["CallChainNode"];

// ── Helpers ─────────────────────────────────────────────────────────────────

const CATEGORY_COLORS = KNOWLEDGE_CATEGORY_COLORS as Record<string, string>;

function getCatColor(cat: string): string {
  return CATEGORY_COLORS[cat] ?? "#6b7280";
}

// ── Components ──────────────────────────────────────────────────────────────

function CategoryPill({ category }: { category: string }) {
  const { t } = useTranslation();
  const color = getCatColor(category);
  const label = t("knowledgeDetail.categories." + category, category);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
      style={{
        backgroundColor: `${color}12`,
        color,
        border: `1px solid ${color}28`,
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    pct >= 80 ? "bg-emerald-400" : pct >= 50 ? "bg-amber-400" : "bg-red-400";
  const textColor =
    pct >= 80 ? "text-emerald-400" : pct >= 50 ? "text-amber-400" : "text-red-400";
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="h-1.5 w-20 rounded-full bg-white/[0.08] overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={textColor}>{pct}%</span>
    </div>
  );
}

/** 代码片段详情（含代码内容） */
function CodeSnippetDetail({ snippet }: { snippet: CodeSnippet }) {
  const filePath = snippet.filePath || "";
  const fileName = filePath.split("/").pop() || filePath.split("\\").pop() || filePath || "unknown";
  const lang = snippet.language || "";
  const content = snippet.content || "";

  return (
    <div className="rounded-xl border border-white/[0.06] overflow-hidden bg-white/[0.01] transition-all hover:bg-white/[0.02]">
      {/* 头部 */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-white/[0.04]">
        <FileCode className="w-4 h-4 text-brand shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium text-[var(--text-primary)] font-mono">
            {fileName}
          </span>
          <span className="text-xs text-[var(--text-muted)] ml-2">
            ({snippet.startLine}-{snippet.endLine})
          </span>
          {lang && (
            <span className="ml-2 px-1.5 py-0.5 rounded bg-brand/[0.08] text-[10px] text-brand">
              {lang}
            </span>
          )}
        </div>
        {snippet.signature && (
          <span className="text-xs text-brand font-mono truncate max-w-[220px] shrink-0">
            {snippet.signature}
          </span>
        )}
      </div>
      {/* 代码内容 */}
      {content && (
        <pre className="px-4 py-3 overflow-x-auto">
          <code className="text-xs text-[var(--text-secondary)] font-mono whitespace-pre-wrap leading-relaxed">
            {content}
          </code>
        </pre>
      )}
    </div>
  );
}

/** 调用链详情 */
function CallChainDetail({ nodes }: { nodes: CallChainNode[] }) {
  const { t } = useTranslation();
  const nodeTypeColors: Record<string, string> = {
    function: "bg-emerald-400/10 text-emerald-400",
    class: "bg-brand/10 text-brand",
    method: "bg-amber-400/10 text-amber-400",
    function_call: "bg-sky-400/10 text-sky-400",
    import: "bg-violet-400/10 text-violet-400",
    module: "bg-orange-400/10 text-orange-400",
    entry: "bg-brand/10 text-brand",
    call: "bg-sky-400/10 text-sky-400",
    implementation: "bg-emerald-400/10 text-emerald-400",
    export: "bg-violet-400/10 text-violet-400",
  };

  return (
    <div className="space-y-2.5">
      {nodes.map((node, i) => {
        const filePath = node.file || "";
        const fileName = filePath.split("/").pop() || filePath.split("\\").pop() || filePath || "";
        const typeColor = nodeTypeColors[node.nodeType] || nodeTypeColors[node.direction] || "bg-white/10 text-[var(--text-secondary)]";
        return (
          <div key={i} className="flex items-center gap-3">
            {/* 连接线 */}
            {i > 0 && (
              <div className="w-8 flex justify-center">
                <div className="w-px h-4 bg-brand/20" />
              </div>
            )}
            {/* 节点卡片 */}
            <div className="flex-1 flex items-center gap-3 rounded-xl bg-white/[0.02] border border-white/[0.05] px-4 py-3 transition-all hover:bg-white/[0.04]">
              <span
                className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-md ${typeColor}`}
              >
                {node.nodeType || node.direction || t("knowledgeDetail.nodeTypes.call")}
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-sm text-[var(--text-primary)] font-mono truncate block">
                  {node.signature || node.nodeId || "—"}
                </span>
                {fileName && (
                  <span className="text-xs text-[var(--text-muted)]">
                    {fileName}
                  </span>
                )}
              </div>
              {i < nodes.length - 1 && (
                <ArrowRight className="w-4 h-4 text-brand/50 shrink-0" />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** 拓展内容完整展示 */
function ExpansionPanel({ expansion }: { expansion: ExpansionContent | null }) {
  const { t } = useTranslation();
  if (!expansion) {
    return (
      <div className="text-center py-10">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white/[0.03] mb-3">
          <Sparkles className="w-5 h-5 text-[var(--text-muted)]" />
        </div>
        <p className="text-sm text-[var(--text-muted)]">{t("knowledgeDetail.sections.noExpand")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {expansion.principle && (
        <div className="rounded-xl bg-brand/[0.04] border border-brand/[0.1] p-5">
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand" /> {t("knowledgeDetail.sections.principle")}
          </h4>
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
            {expansion.principle}
          </p>
        </div>
      )}

      {expansion.applicableScenarios?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2.5">{t("knowledgeDetail.sections.scenario")}</h4>
          <div className="space-y-1.5">
            {expansion.applicableScenarios.map((s: string, i: number) => (
              <div key={i} className="flex items-start gap-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04] px-4 py-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand/70" />
                <span className="text-sm text-[var(--text-secondary)]">{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {expansion.bestPractices?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2.5">{t("knowledgeDetail.sections.bestPractice")}</h4>
          <div className="space-y-1.5">
            {expansion.bestPractices.map((p: string, i: number) => (
              <div key={i} className="flex items-start gap-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04] px-4 py-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400/80" />
                <span className="text-sm text-[var(--text-secondary)]">{p}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {expansion.relatedPatterns?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2.5">{t("knowledgeDetail.sections.related")}</h4>
          <div className="flex flex-wrap gap-1.5">
            {expansion.relatedPatterns.map((r: string, i: number) => (
              <span
                key={i}
                className="inline-flex items-center rounded-lg bg-white/[0.04] border border-white/[0.06] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] transition-colors hover:bg-white/[0.08]"
              >
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {expansion.learningResources?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2.5">{t("knowledgeDetail.sections.resources")}</h4>
          <div className="space-y-1.5">
            {expansion.learningResources.map((r, i: number) => (
              <a
                key={i}
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-xl bg-white/[0.02] border border-white/[0.04] px-4 py-3 text-sm text-[var(--text-secondary)] hover:bg-white/[0.05] transition-all group"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-[10px] uppercase font-bold text-[var(--text-muted)] shrink-0 w-12">
                    {t("knowledgeDetail.resourceTypes." + r.type, r.type)}
                  </span>
                  <span className="truncate">{r.title}</span>
                </div>
                <ExternalLink className="w-4 h-4 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-brand" />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Section Header ──────────────────────────────────────────────────────────

function SectionHeader({
  icon,
  title,
  count,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
}) {
  return (
    <div className="flex items-center gap-2.5 mb-5">
      <div className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-brand/[0.1]">
        {icon}
      </div>
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
      {count !== undefined && count > 0 && (
        <span className="text-xs text-[var(--text-muted)] font-mono">{count}</span>
      )}
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function KnowledgeDetailPage() {
  const { t } = useTranslation();
  const params = useParams();
  const id = params.id as string;

  const { data: kp, isLoading, error } = useQuery<KnowledgePoint>({
    queryKey: ["knowledge-point", id],
    queryFn: () => getKnowledgePoint(id),
    enabled: !!id,
  });

  const catColor = kp ? getCatColor(kp.category) : undefined;

  if (isLoading) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-16">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-40 bg-white/[0.06] rounded mb-8" />
          <div className="h-4 w-20 bg-white/[0.06] rounded mb-3" />
          <div className="h-6 w-3/4 bg-white/[0.06] rounded mb-2" />
          <div className="h-4 w-full bg-white/[0.06] rounded mb-8" />
          <div className="h-32 bg-white/[0.06] rounded" />
        </div>
      </main>
    );
  }

  if (error || !kp) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-16 text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white/[0.03] mb-4">
          <FileText className="w-8 h-8 text-[var(--text-muted)] opacity-50" />
        </div>
        <h2 className="text-xl font-semibold text-[var(--text-primary)]">{t("knowledgeDetail.notFound")}</h2>
        <p className="mt-2 text-sm text-[var(--text-muted)]">{t("knowledgeDetail.notFoundDesc")}</p>
        <Link
          href="/knowledge"
          className="inline-flex items-center gap-2 mt-6 px-4 py-2 rounded-lg bg-brand/[0.1] text-brand hover:bg-brand/[0.15] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          {t("knowledgeDetail.back")}
        </Link>
      </main>
    );
  }

  const snippets = kp.codeSnippets || [];
  const nodes = kp.callChain || [];
  const expansion = kp.expansion || null;

  return (
    <main className="mx-auto max-w-4xl px-6 py-16">
      {/* 背景装饰 */}
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div
          className="absolute top-[-15%] right-[-10%] w-[500px] h-[500px] rounded-full blur-[120px]"
          style={{ backgroundColor: `${catColor}10` }}
        />
      </div>

      {/* 返回按钮 */}
      <div className="mb-8">
        <Link
          href="/knowledge"
          className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] text-sm text-[var(--text-secondary)] hover:bg-white/[0.06] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          {t("knowledgeDetail.back")}
        </Link>
      </div>

      {/* 头部 */}
      <header className="mb-10 relative">
        <div
          className="absolute -top-6 -left-4 w-40 h-40 rounded-full blur-[80px]"
          style={{ backgroundColor: `${catColor}20` }}
        />
        <div className="flex items-center gap-3 mb-4 relative">
          <CategoryPill category={kp.category} />
          <ConfidenceBar confidence={kp.confidence} />
        </div>
        <h1 className="text-3xl font-bold text-[var(--text-primary)] leading-tight relative">
          {kp.title}
        </h1>
        <p className="mt-4 text-base text-[var(--text-secondary)] leading-relaxed max-w-2xl">
          {kp.description}
        </p>
        {kp.tags?.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {kp.tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 rounded-md bg-white/[0.04] px-2.5 py-1 text-xs text-[var(--text-secondary)]"
              >
                <Tag className="w-3 h-3" />
                {tag}
              </span>
            ))}
          </div>
        )}
      </header>

      {/* 应用流程（调用链） */}
      {nodes.length > 0 && (
        <section className="mb-10">
          <SectionHeader
            icon={<GitBranch className="w-4 h-4 text-brand" />}
            title={t("knowledgeDetail.sections.flow")}
            count={nodes.length}
          />
          <CallChainDetail nodes={nodes} />
        </section>
      )}

      {/* 代码片段 */}
      {snippets.length > 0 && (
        <section className="mb-10">
          <SectionHeader
            icon={<Code2 className="w-4 h-4 text-brand" />}
            title={t("knowledgeDetail.sections.codeSnippets")}
            count={snippets.length}
          />
          <div className="space-y-3">
            {snippets.map((snippet, i) => (
              <CodeSnippetDetail key={i} snippet={snippet} />
            ))}
          </div>
        </section>
      )}

      {/* 拓展内容 */}
      <section>
        <SectionHeader
          icon={<Sparkles className="w-4 h-4 text-brand" />}
          title={t("knowledgeDetail.sections.expand")}
        />
        <ExpansionPanel expansion={expansion} />
      </section>

      {/* 底部 */}
      <div className="mt-12 pt-8 border-t border-white/[0.06] flex items-center justify-between text-sm text-[var(--text-muted)]">
        <div className="flex items-center gap-4">
          {kp.createdAt && (
            <span>{t("knowledgeDetail.createdAt", { d: new Date(kp.createdAt).toLocaleDateString() })}</span>
          )}
          {kp.updatedAt && kp.updatedAt !== kp.createdAt && (
            <span>{t("knowledgeDetail.updatedAt", { d: new Date(kp.updatedAt).toLocaleDateString() })}</span>
          )}
        </div>
        <span className="font-mono text-[var(--text-muted)]">v{kp.version || "—"}</span>
      </div>
    </main>
  );
}