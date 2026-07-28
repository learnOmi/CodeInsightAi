"use client";

import { useTranslation } from "react-i18next";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BookOpen, FolderOpen, Search, ArrowLeft, ArrowRight, House } from "lucide-react";
import { cn } from "@/utils";

export function GlobalNav() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();

  const navItems = [
    {
      label: t("nav.repository"),
      href: "/repositories",
      icon: FolderOpen,
      match: (path: string) => path.startsWith("/repositories") && !path.startsWith("/repositories/"),
    },
    {
      label: t("nav.knowledgeShort"),
      href: "/knowledge",
      icon: BookOpen,
      match: (path: string) => path.startsWith("/knowledge"),
    },
    {
      label: t("nav.search"),
      href: "/search",
      icon: Search,
      match: (path: string) => path.startsWith("/search"),
    },
  ];

  return (
    <nav className="sticky top-2 z-50">
      <div className="mx-auto w-fit">
        <div className="flex items-center gap-0.5 rounded-full border border-white/[0.06] bg-[var(--bg-card)]/70 backdrop-blur-xl px-1 py-1 shadow-sm">
          {/* 主页 */}
          <Link
            href="/"
            className={cn(
              "flex items-center justify-center w-8 h-8 rounded-full text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white/[0.06] transition-all duration-300 ease-out shrink-0 active:scale-95",
              pathname === "/" && "bg-brand/12 text-brand"
            )}
            title={t("nav.home")}
          >
            <House className="w-4 h-4" />
          </Link>

          <div className="w-px h-5 bg-white/[0.06] mx-1 shrink-0" />

          {/* 后退/前进 */}
          <button
            onClick={() => router.back()}
            className="flex items-center justify-center w-8 h-8 rounded-full text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white/[0.06] transition-all duration-300 ease-out shrink-0 active:scale-95"
            title={t("nav.back")}
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => router.forward()}
            className="flex items-center justify-center w-8 h-8 rounded-full text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white/[0.06] transition-all duration-300 ease-out shrink-0 active:scale-95"
            title={t("nav.forward")}
          >
            <ArrowRight className="w-4 h-4" />
          </button>

          <div className="w-px h-5 bg-white/[0.06] mx-1 shrink-0" />

          {/* 导航项 */}
          {navItems.map(({ label, href, icon: Icon, match }) => {
            const isActive = match(pathname);
            return (
              <Link
                key={label}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-300 ease-out whitespace-nowrap active:scale-95",
                  isActive
                    ? "bg-brand/12 text-brand shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white/[0.04]"
                )}
              >
                <Icon className={cn("w-3.5 h-3.5 transition-transform duration-300 ease-out", isActive && "text-brand")} />
                <span>{label}</span>
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}