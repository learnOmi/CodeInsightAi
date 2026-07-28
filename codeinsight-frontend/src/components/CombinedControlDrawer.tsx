"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { Minus, Moon, Sun, Globe, Settings } from "lucide-react";

const LOCALE_STORAGE_KEY = "codeinsight_locale";

export function CombinedControlDrawer() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const mainBtnRef = useRef<HTMLButtonElement>(null);
  const [currentLocale, setCurrentLocale] = useState(i18n.language ?? "zh-CN");
  const [themeDark, setThemeDark] = useState(false);

  // 🔥 修复问题3：正确从localStorage读取初始主题状态（只在首次挂载时）
  useEffect(() => {
    const stored = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    let shouldBeDark;

    if (stored === "dark") {
      shouldBeDark = true;
    } else if (stored === "light") {
      shouldBeDark = false;
    } else {
      shouldBeDark = prefersDark;
    }

    // 只设置一次，不重复写入
    const hasDarkClass = document.documentElement.classList.contains("dark");
    if (hasDarkClass !== shouldBeDark) {
      document.documentElement.classList.toggle("dark", shouldBeDark);
    }

    setThemeDark(shouldBeDark);
  }, []);

  // 🔁 同步主题变化（只监听，不初始化）
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setThemeDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  const toggleLocale = () => {
    const next = currentLocale === "zh-CN" ? "en-US" : "zh-CN";
    localStorage.setItem(LOCALE_STORAGE_KEY, next);
    i18n.changeLanguage(next);
    setCurrentLocale(next);
  };

  const toggleTheme = () => {
    const next = !themeDark;
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
    setThemeDark(next);
  };

  const toggleOpen = () => setOpen(!open);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      const inside = toolbarRef.current?.contains(e.target as Node) || mainBtnRef.current?.contains(e.target as Node);
      if (!inside) setOpen(false);
    };
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [open]);

  // ESC关闭
  useEffect(() => {
    const handle = (e: KeyboardEvent) => { if (e.key === "Escape" && open) setOpen(false); };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [open]);

  return (
    <>
      {/* 左下角固定容器 */}
      <div className="relative" style={{ zIndex: 60, position: "fixed", bottom: "1rem", left: "1.5rem" }}>

        {/* 工具栏主体 - 从圆形扩展为横向胶囊 */}
        <motion.div
          ref={toolbarRef}
          initial={{ width: 48, height: 48, borderRadius: "9999px", padding: "6px" }}
          animate={open
            ? { width: 144, height: 48, borderRadius: 24, padding: "6px 8px 6px 6px" } // 🔥 减少右侧空白
            : { width: 48, height: 48, borderRadius: "9999px", padding: "6px" }
          }
          transition={{ type: "spring", stiffness: 340, damping: 26, bounceDelay: 0.12 }}
          className={`bg-white/[0.25] dark:bg-slate-700/[60] backdrop-blur-xl backdrop-saturate-150 border border-white/[0.3] dark:border-slate-600 shadow-lg flex items-center gap-0 overflow-hidden ${open ? "cursor-default" : "cursor-pointer"}`}
        >
          {/* 左侧主按钮 - 齿轮图标 */}
          <motion.button
            ref={mainBtnRef}
            onClick={(e) => { e.stopPropagation(); toggleOpen(); }}
            className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-105 focus:outline-none ${
              open
                ? "bg-white/25 dark:bg-slate-600/[40] hover:bg-white/35 dark:hover:bg-slate-600/[50]"
                : "bg-white/20 dark:bg-slate-700/[50] hover:bg-white/30 dark:hover:bg-slate-600/[50]"
            }`}
            title={open ? t("controls.close") : t("controls.open")}
          >
            {/* 🔥 修复：无边框、居中完美 */}
            <motion.div animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.5, cubicBezier: "[0.34,1.56,0.64,1]" }}>
              {open ? (
                <Minus className="w-4 h-4 text-[var(--text-primary)]" />
              ) : (
                <Settings className="w-4 h-4 text-[var(--text-primary)]" />
              )}
            </motion.div>
          </motion.button>

          {/* 功能图标区 - 紧凑排列 🔥修复挤压问题 */}
          <div className="flex items-center gap-2 flex-0 shrink-0" style={{ opacity: open ? 1 : 0, transition: "opacity 0.18s ease" }}>

            {/* 语言切换 - 圆形图标按钮 */}
            <motion.button
              key="lang"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.045, type: "spring", stiffness: 320, damping: 21 }}
              onClick={(e) => { e.stopPropagation(); toggleLocale(); }}
              className="flex-shrink-0 w-9 h-9 rounded-full bg-white/15 dark:bg-slate-600/[30] border border-white/10 dark:border-transparent flex items-center justify-center transition-all duration-300 hover:bg-white/25 dark:hover:bg-slate-500/[40] hover:scale-110 focus:outline-none"
              title={t("language.toggle")}
              tabIndex={0}
            >
              <Globe className="w-3.5 h-3.5 text-[var(--text-secondary)] dark:text-[var(--text-primary)]" />
            </motion.button>

            {/* 主题切换 - 圆形图标按钮 */}
            <motion.button
              key="theme"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.095, type: "spring", stiffness: 320, damping: 21 }}
              onClick={toggleTheme}
              className="flex-shrink-0 w-9 h-9 rounded-full bg-white/15 dark:bg-slate-600/[30] border border-white/10 dark:border-transparent flex items-center justify-center transition-all duration-300 hover:bg-white/25 dark:hover:bg-slate-500/[40] hover:scale-110 focus:outline-none"
              title={t("theme.toggle")}
              tabIndex={0}
            >
              {themeDark ? (
                <Sun className="w-3.5 h-3.5 text-amber-400" />
              ) : (
                <Moon className="w-3.5 h-3.5 text-[var(--text-secondary)] dark:text-[var(--text-primary)]" />
              )}
            </motion.button>

          </div>
        </motion.div>
      </div>
    </>
  );
}