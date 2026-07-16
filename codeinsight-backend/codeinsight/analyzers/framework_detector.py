"""
FrameworkDetector - 框架检测引擎

通过文件级扫描、AST 级分析、依赖级分析三个层面检测项目使用的框架和技术栈。

检测流程：
1. 文件级检测（最快，零解析成本）：通过文件路径、文件内容模式匹配
2. AST 级检测（精确）：通过注解/装饰器/命名模式识别框架角色
3. 依赖级检测（确认）：通过 package.json/pom.xml 等确认框架版本

输出：框架检测结果，写入 framework_patterns 表

架构说明：
采用策略模式 + 注册机制（FrameworkSignatureRegistry），将框架签名规则与检测逻辑解耦。
新增框架检测只需通过 register_* 方法注册签名规则，无需修改 detect_file_level /
detect_ast_level 等检测方法。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codeinsight.parsers.base import ASTNodeList

logger = logging.getLogger(__name__)


# ---------------- 置信度常量 ----------------
# 文件级：每命中一个内容模式增加 0.1，单框架最高 0.3
FILE_CONTENT_MATCH_CONFIDENCE = 0.1
FILE_LEVEL_MAX_CONFIDENCE = 0.3
# 扩展名级：每命中一个文件增加 0.05，单框架最高 0.2
EXTENSION_MATCH_CONFIDENCE = 0.05
EXTENSION_MAX_CONFIDENCE = 0.2
# AST 级：tag 匹配每命中一次增加 0.1，最高 0.4
AST_TAG_MATCH_CONFIDENCE = 0.1
AST_TAG_MAX_CONFIDENCE = 0.4
# AST 级：annotation 匹配每命中一次增加 0.1；与 tag 合并时单次上限 0.2，单独命中上限 0.4
AST_ANNOTATION_MATCH_CONFIDENCE = 0.1
AST_ANNOTATION_COMBINED_MAX_CONFIDENCE = 0.2
AST_ANNOTATION_SOLO_MAX_CONFIDENCE = 0.4
# 综合置信度上限
OVERALL_MAX_CONFIDENCE = 1.0


class FrameworkPattern:
    """
    框架检测结果

    Attributes:
        framework: 框架标识（spring_boot, react, vue, express, flask 等）
        category: 框架类别（frontend, backend, database, messaging 等）
        confidence: 检测置信度 0.0-1.0
        evidence: 检测依据（文件路径、配置项、版本号等）
    """

    def __init__(
        self,
        framework: str,
        category: str,
        confidence: float = 0.0,
        evidence: dict | None = None,
    ) -> None:
        self.framework = framework
        self.category = category
        self.confidence = confidence
        self.evidence = evidence or {}

    def to_dict(self) -> dict:
        """转为字典"""
        return {
            "framework": self.framework,
            "category": self.category,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class FileSignature:
    """
    文件级签名规则

    Attributes:
        framework: 框架标识
        category: 框架类别
        files: 触发文件名列表（如 package.json、pom.xml）
        content_patterns: 文件内容子串匹配模式列表
        version_pattern: 版本号正则（可选）
    """

    framework: str
    category: str
    files: list[str]
    content_patterns: list[str] = field(default_factory=list)
    version_pattern: str | None = None


@dataclass
class ExtensionSignature:
    """
    扩展名签名规则

    Attributes:
        framework: 框架标识
        category: 框架类别
        extensions: 扩展名列表（如 .vue、.tsx）
    """

    framework: str
    category: str
    extensions: list[str]


@dataclass
class AstSignature:
    """
    AST 级签名规则

    Attributes:
        framework: 框架标识
        category: 框架类别
        language: 限定语言（空字符串表示不限）
        tags: 节点 tag 精确匹配列表
        annotations: 注解前缀匹配列表（使用 startswith 语义）
        decorators: 装饰器名称列表（预留扩展位）
        calls: 调用名称列表（预留扩展位）
    """

    framework: str
    category: str
    language: str = ""
    tags: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)


class FrameworkSignatureRegistry:
    """
    框架签名注册表

    采用策略模式 + 注册机制：将框架签名规则与检测逻辑解耦。
    新增框架检测只需通过 register_* 方法注册签名，无需修改 detect_by_* 检测方法。

    支持三类签名：
    - 文件签名（FileSignature）：通过特定文件名 + 内容模式匹配
    - 扩展名签名（ExtensionSignature）：通过文件扩展名匹配
    - AST 签名（AstSignature）：通过节点 tags / annotations 匹配
    """

    def __init__(self) -> None:
        self._file_signatures: list[FileSignature] = []
        self._extension_signatures: list[ExtensionSignature] = []
        self._ast_signatures: list[AstSignature] = []

    # ---------------- 注册方法 ----------------

    def register_file_signature(
        self,
        framework: str,
        category: str,
        file_patterns: list[str],
        content_patterns: list[str] | None = None,
        version_pattern: str | None = None,
    ) -> None:
        """
        注册文件级签名

        Args:
            framework: 框架标识
            category: 框架类别
            file_patterns: 触发文件名列表（如 ["package.json"]）
            content_patterns: 文件内容子串匹配模式列表
            version_pattern: 版本号正则（可选）
        """
        self._file_signatures.append(
            FileSignature(
                framework=framework,
                category=category,
                files=list(file_patterns),
                content_patterns=list(content_patterns or []),
                version_pattern=version_pattern,
            )
        )

    def register_extension_signature(
        self,
        framework: str,
        category: str,
        extensions: list[str],
    ) -> None:
        """
        注册扩展名签名

        Args:
            framework: 框架标识
            category: 框架类别
            extensions: 扩展名列表（如 [".vue", ".tsx"]）
        """
        self._extension_signatures.append(
            ExtensionSignature(
                framework=framework,
                category=category,
                extensions=list(extensions),
            )
        )

    def register_ast_signature(
        self,
        framework: str,
        category: str,
        language: str = "",
        tags: list[str] | None = None,
        annotations: list[str] | None = None,
        decorators: list[str] | None = None,
        calls: list[str] | None = None,
    ) -> None:
        """
        注册 AST 级签名

        Args:
            framework: 框架标识
            category: 框架类别
            language: 限定语言（空字符串表示不限）
            tags: 节点 tag 精确匹配列表
            annotations: 注解前缀匹配列表（使用 startswith 语义）
            decorators: 装饰器名称列表（预留扩展位）
            calls: 调用名称列表（预留扩展位）
        """
        self._ast_signatures.append(
            AstSignature(
                framework=framework,
                category=category,
                language=language,
                tags=list(tags or []),
                annotations=list(annotations or []),
                decorators=list(decorators or []),
                calls=list(calls or []),
            )
        )

    # ---------------- 只读视图 ----------------

    @property
    def file_signatures(self) -> list[FileSignature]:
        """文件签名列表（只读视图）"""
        return self._file_signatures

    @property
    def extension_signatures(self) -> list[ExtensionSignature]:
        """扩展名签名列表（只读视图）"""
        return self._extension_signatures

    @property
    def ast_signatures(self) -> list[AstSignature]:
        """AST 签名列表（只读视图）"""
        return self._ast_signatures

    def get_trigger_file_names(self) -> list[str]:
        """
        返回所有文件签名中需要触发的文件名列表（去重，保留注册顺序）

        Returns:
            触发文件名列表
        """
        seen: dict[str, None] = {}
        for sig in self._file_signatures:
            for name in sig.files:
                seen[name] = None
        return list(seen.keys())

    # ---------------- 检测方法 ----------------

    def detect_by_file(self, file_path: Path) -> list[FrameworkPattern]:
        """
        文件级检测：基于单个文件路径与内容匹配

        若文件名命中某 FileSignature 的触发文件列表，则读取文件内容，
        按 content_patterns 子串匹配累计置信度，并按 version_pattern 提取版本号。

        Args:
            file_path: 待检测文件路径

        Returns:
            命中的框架检测结果列表（每个命中的框架一个元素）
        """
        results: list[FrameworkPattern] = []
        if not file_path.exists() or not file_path.is_file():
            return results

        file_name = file_path.name
        matched_signatures = [s for s in self._file_signatures if file_name in s.files]
        if not matched_signatures:
            return results

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取文件失败 %s: %s", file_path, exc)
            return results

        for sig in matched_signatures:
            confidence = 0.0
            evidence: dict[str, Any] = {}

            for pattern in sig.content_patterns:
                if pattern in content:
                    confidence += FILE_CONTENT_MATCH_CONFIDENCE
                    evidence.setdefault("files", []).append(file_name)

                    if sig.version_pattern:
                        match = re.search(sig.version_pattern, content)
                        if match:
                            evidence["version"] = match.group(1)

            if confidence > 0:
                results.append(
                    FrameworkPattern(
                        framework=sig.framework,
                        category=sig.category,
                        confidence=min(confidence, FILE_LEVEL_MAX_CONFIDENCE),
                        evidence=evidence,
                    )
                )

        return results

    def detect_by_extension(self, file_path: Path) -> list[FrameworkPattern]:
        """
        扩展名检测：基于单个文件路径的扩展名匹配

        每命中一个 ExtensionSignature 返回一个 FrameworkPattern，
        单次置信度为 EXTENSION_MATCH_CONFIDENCE；调用方负责按框架聚合计数。

        Args:
            file_path: 待检测文件路径

        Returns:
            命中的框架检测结果列表（每个命中的签名一个元素）
        """
        results: list[FrameworkPattern] = []
        file_name = file_path.name

        for sig in self._extension_signatures:
            for ext in sig.extensions:
                if file_name.endswith(ext):
                    results.append(
                        FrameworkPattern(
                            framework=sig.framework,
                            category=sig.category,
                            confidence=EXTENSION_MATCH_CONFIDENCE,
                            evidence={"file_count": 1},
                        )
                    )
                    break  # 单个签名命中一次即可，继续检查下一个签名

        return results

    def detect_by_ast(self, nodes: ASTNodeList) -> list[FrameworkPattern]:
        """
        AST 级检测：基于 AST 节点的 tags / annotations 匹配

        检测流程：
        1. 统计所有节点的 tag_counts 与 annotation_counts
        2. 遍历 AstSignature，按 tags 精确匹配累计各框架命中数
        3. 遍历 AstSignature，按 annotations 前缀匹配累计各框架命中数
        4. 合并 tag / annotation 结果，annotation 命中会叠加到已有 tag 结果上

        Args:
            nodes: AST 节点列表

        Returns:
            框架检测结果列表
        """
        tag_counts: dict[str, int] = {}
        annotation_counts: dict[str, int] = {}

        for node in nodes.nodes:
            for tag in node.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

            for annotation in node.annotations:
                ann_name = annotation.get("name", "")
                annotation_counts[ann_name] = annotation_counts.get(ann_name, 0) + 1

        # 框架 -> 类别映射（取首次注册的类别，兼容多签名场景）
        framework_category: dict[str, str] = {}
        for sig in self._ast_signatures:
            framework_category.setdefault(sig.framework, sig.category)

        # tag 匹配：每个 tag 精确匹配，累计到所属框架
        tag_framework_counts: dict[str, int] = {}
        for sig in self._ast_signatures:
            for tag in sig.tags:
                if tag in tag_counts:
                    tag_framework_counts[sig.framework] = tag_framework_counts.get(sig.framework, 0) + tag_counts[tag]

        results: list[FrameworkPattern] = []
        for framework, count in tag_framework_counts.items():
            category = framework_category.get(framework, "other")
            results.append(
                FrameworkPattern(
                    framework=framework,
                    category=category,
                    confidence=min(count * AST_TAG_MATCH_CONFIDENCE, AST_TAG_MAX_CONFIDENCE),
                    evidence={"tag_matches": count},
                )
            )

        # annotation 匹配：前缀匹配，首个命中的签名胜出（与原 if-elif 行为一致）
        annotation_framework_counts: dict[str, int] = {}
        for ann_name, count in annotation_counts.items():
            for sig in self._ast_signatures:
                if any(ann_name.startswith(p) for p in sig.annotations):
                    annotation_framework_counts[sig.framework] = (
                        annotation_framework_counts.get(sig.framework, 0) + count
                    )
                    break  # 单个 annotation 只归属首个命中的框架

        for framework, count in annotation_framework_counts.items():
            found = False
            for result in results:
                if result.framework == framework:
                    result.confidence += min(
                        count * AST_ANNOTATION_MATCH_CONFIDENCE,
                        AST_ANNOTATION_COMBINED_MAX_CONFIDENCE,
                    )
                    result.confidence = min(result.confidence, OVERALL_MAX_CONFIDENCE)
                    result.evidence["annotation_matches"] = count
                    found = True
                    break
            if not found:
                category = framework_category.get(framework, "other")
                results.append(
                    FrameworkPattern(
                        framework=framework,
                        category=category,
                        confidence=min(
                            count * AST_ANNOTATION_MATCH_CONFIDENCE,
                            AST_ANNOTATION_SOLO_MAX_CONFIDENCE,
                        ),
                        evidence={"annotation_matches": count},
                    )
                )

        return results


class FrameworkDetector:
    """
    框架检测引擎

    支持三种检测级别：文件级、AST 级、依赖级。
    采用注册机制：内置签名在 __init__ 中通过 _register_default_signatures 注册，
    外部可通过 register_* 方法扩展，无需修改检测方法。
    """

    def __init__(self) -> None:
        self.registry = FrameworkSignatureRegistry()
        self._register_default_signatures()

    def _register_default_signatures(self) -> None:
        """注册内置框架签名（保留原有检测能力）"""
        # ---------- 文件级签名 ----------
        self.registry.register_file_signature(
            framework="spring_boot",
            category="backend",
            file_patterns=["pom.xml", "build.gradle", "build.gradle.kts"],
            content_patterns=["spring-boot-starter", "org.springframework.boot"],
            version_pattern=r"<version>([\d.]+)</version>",
        )
        self.registry.register_file_signature(
            framework="react",
            category="frontend",
            file_patterns=["package.json"],
            content_patterns=['"react":', '"react-dom":'],
            version_pattern=r'"react"\s*:\s*"([^"]+)"',
        )
        self.registry.register_file_signature(
            framework="vue",
            category="frontend",
            file_patterns=["package.json"],
            content_patterns=['"vue":'],
            version_pattern=r'"vue"\s*:\s*"([^"]+)"',
        )
        self.registry.register_file_signature(
            framework="angular",
            category="frontend",
            file_patterns=["package.json"],
            content_patterns=['"@angular/core":', '"@angular/common":'],
            version_pattern=r'"@angular/core"\s*:\s*"([^"]+)"',
        )
        self.registry.register_file_signature(
            framework="express",
            category="backend",
            file_patterns=["package.json"],
            content_patterns=['"express":'],
            version_pattern=r'"express"\s*:\s*"([^"]+)"',
        )
        self.registry.register_file_signature(
            framework="flask",
            category="backend",
            file_patterns=["requirements.txt", "Pipfile", "pyproject.toml", "setup.py"],
            content_patterns=["flask", "Flask"],
            version_pattern=r"flask[>=~]=?\s*([\d.]+)",
        )
        self.registry.register_file_signature(
            framework="fastapi",
            category="backend",
            file_patterns=["requirements.txt", "Pipfile", "pyproject.toml", "setup.py"],
            content_patterns=["fastapi", "FastAPI"],
            version_pattern=r"fastapi[>=~]=?\s*([\d.]+)",
        )
        self.registry.register_file_signature(
            framework="django",
            category="backend",
            file_patterns=["requirements.txt", "Pipfile", "pyproject.toml", "setup.py"],
            content_patterns=["django", "Django"],
            version_pattern=r"django[>=~]=?\s*([\d.]+)",
        )
        self.registry.register_file_signature(
            framework="gin",
            category="backend",
            file_patterns=["go.mod"],
            content_patterns=["gin-gonic/gin"],
            version_pattern=r"github\.com/gin-gonic/gin\s+v([\d.]+)",
        )
        self.registry.register_file_signature(
            framework="echo",
            category="backend",
            file_patterns=["go.mod"],
            content_patterns=["labstack/echo"],
            version_pattern=r"github\.com/labstack/echo\s+v([\d.]+)",
        )
        self.registry.register_file_signature(
            framework="nestjs",
            category="backend",
            file_patterns=["package.json"],
            content_patterns=['"@nestjs/core":'],
            version_pattern=r'"@nestjs/core"\s*:\s*"([^"]+)"',
        )

        # ---------- 扩展名签名 ----------
        self.registry.register_extension_signature(framework="vue", category="frontend", extensions=[".vue"])
        self.registry.register_extension_signature(framework="react", category="frontend", extensions=[".tsx", ".jsx"])
        self.registry.register_extension_signature(
            framework="angular",
            category="frontend",
            extensions=[".component.ts", ".module.ts"],
        )
        self.registry.register_extension_signature(framework="java", category="backend", extensions=[".java"])
        self.registry.register_extension_signature(framework="python", category="backend", extensions=[".py"])
        self.registry.register_extension_signature(framework="go", category="backend", extensions=[".go"])

        # ---------- AST 级签名 ----------
        self.registry.register_ast_signature(
            framework="react",
            category="frontend",
            tags=["react-component", "react-hook", "react-context"],
        )
        self.registry.register_ast_signature(
            framework="vue",
            category="frontend",
            tags=["vue-component", "vue-composable", "vue-lifecycle", "vue-component-api"],
        )
        self.registry.register_ast_signature(
            framework="spring_boot",
            category="backend",
            tags=[
                "http-controller",
                "business-service",
                "data-repository",
                "spring-component",
                "spring-config",
                "spring-aspect",
            ],
            annotations=[
                "@RestController",
                "@Controller",
                "@Service",
                "@Repository",
                "@Component",
                "@Configuration",
                "@Autowired",
                "@GetMapping",
                "@PostMapping",
                "@SpringBootApplication",
            ],
        )
        self.registry.register_ast_signature(
            framework="flask",
            category="backend",
            tags=["flask-route"],
            annotations=["@app.route"],
        )
        self.registry.register_ast_signature(
            framework="fastapi",
            category="backend",
            tags=["fastapi-route"],
            annotations=["@app.get", "@app.post", "@router.get", "@router.post"],
        )
        self.registry.register_ast_signature(
            framework="celery",
            category="backend",
            tags=["celery-task"],
        )
        self.registry.register_ast_signature(
            framework="gin",
            category="backend",
            tags=["http-handler"],
        )

    # ---------------- 对外注册接口（委托给注册表） ----------------

    def register_file_signature(
        self,
        framework: str,
        category: str,
        file_patterns: list[str],
        content_patterns: list[str] | None = None,
        version_pattern: str | None = None,
    ) -> None:
        """
        注册文件级签名（委托给注册表）

        Args:
            framework: 框架标识
            category: 框架类别
            file_patterns: 触发文件名列表
            content_patterns: 文件内容子串匹配模式列表
            version_pattern: 版本号正则（可选）
        """
        self.registry.register_file_signature(
            framework=framework,
            category=category,
            file_patterns=file_patterns,
            content_patterns=content_patterns,
            version_pattern=version_pattern,
        )

    def register_extension_signature(
        self,
        framework: str,
        category: str,
        extensions: list[str],
    ) -> None:
        """
        注册扩展名签名（委托给注册表）

        Args:
            framework: 框架标识
            category: 框架类别
            extensions: 扩展名列表
        """
        self.registry.register_extension_signature(
            framework=framework,
            category=category,
            extensions=extensions,
        )

    def register_ast_signature(
        self,
        framework: str,
        category: str,
        language: str = "",
        tags: list[str] | None = None,
        annotations: list[str] | None = None,
        decorators: list[str] | None = None,
        calls: list[str] | None = None,
    ) -> None:
        """
        注册 AST 级签名（委托给注册表）

        Args:
            framework: 框架标识
            category: 框架类别
            language: 限定语言（空字符串表示不限）
            tags: 节点 tag 精确匹配列表
            annotations: 注解前缀匹配列表
            decorators: 装饰器名称列表（预留扩展位）
            calls: 调用名称列表（预留扩展位）
        """
        self.registry.register_ast_signature(
            framework=framework,
            category=category,
            language=language,
            tags=tags,
            annotations=annotations,
            decorators=decorators,
            calls=calls,
        )

    # ---------------- 检测入口 ----------------

    def detect(self, repo_path: str | Path, nodes: ASTNodeList | None = None) -> list[FrameworkPattern]:
        """
        完整检测流程

        Args:
            repo_path: 仓库路径
            nodes: AST 节点列表（可选，用于 AST 级检测）

        Returns:
            框架检测结果列表
        """
        results = {}

        file_level_results = self.detect_file_level(repo_path)
        for pattern in file_level_results:
            results[pattern.framework] = pattern

        if nodes:
            ast_level_results = self.detect_ast_level(nodes)
            for pattern in ast_level_results:
                if pattern.framework in results:
                    results[pattern.framework].confidence += pattern.confidence
                    results[pattern.framework].evidence.update(pattern.evidence)
                else:
                    results[pattern.framework] = pattern

        for key in results:
            results[key].confidence = min(results[key].confidence, 1.0)

        return list(results.values())

    def detect_file_level(self, repo_path: str | Path) -> list[FrameworkPattern]:
        """
        文件级检测

        通过文件路径和内容模式匹配检测框架。检测逻辑委托给注册表：
        - 文件签名：遍历注册表中所有触发文件名，调用 registry.detect_by_file 进行内容匹配
        - 扩展名签名：遍历目录树，调用 registry.detect_by_extension 按框架聚合计数

        Args:
            repo_path: 仓库路径

        Returns:
            框架检测结果列表
        """
        results: list[FrameworkPattern] = []
        path = Path(repo_path)

        if not path.exists() or not path.is_dir():
            return results

        # 文件签名检测：按框架聚合多个触发文件的结果
        aggregated: dict[str, FrameworkPattern] = {}
        for file_name in self.registry.get_trigger_file_names():
            file_path = path / file_name
            if not file_path.exists():
                continue
            for pattern in self.registry.detect_by_file(file_path):
                if pattern.framework in aggregated:
                    existing = aggregated[pattern.framework]
                    existing.confidence = min(
                        existing.confidence + pattern.confidence,
                        FILE_LEVEL_MAX_CONFIDENCE,
                    )
                    existing.evidence.setdefault("files", []).extend(pattern.evidence.get("files", []))
                    if "version" in pattern.evidence:
                        existing.evidence["version"] = pattern.evidence["version"]
                else:
                    aggregated[pattern.framework] = pattern
        results.extend(aggregated.values())

        # 扩展名检测
        ext_results = self._detect_by_extensions(path)
        results.extend(ext_results)

        return results

    def _detect_by_extensions(self, repo_path: Path) -> list[FrameworkPattern]:
        """
        通过文件扩展名检测框架

        遍历目录树，调用 registry.detect_by_extension 对每个文件做扩展名匹配，
        按框架聚合计数后计算置信度。

        Args:
            repo_path: 仓库路径

        Returns:
            框架检测结果列表
        """
        ext_count: dict[str, int] = {}
        category_map: dict[str, str] = {}

        for _root, _, files in repo_path.walk():
            for file in files:
                file_path = Path(file)
                seen_frameworks: set[str] = set()
                for pattern in self.registry.detect_by_extension(file_path):
                    # 同一文件对同一框架只计一次（与原 dict 行为一致）
                    if pattern.framework in seen_frameworks:
                        continue
                    seen_frameworks.add(pattern.framework)
                    ext_count[pattern.framework] = ext_count.get(pattern.framework, 0) + 1
                    category_map[pattern.framework] = pattern.category

        results = []
        for framework, count in ext_count.items():
            if count >= 1:
                confidence = min(count * EXTENSION_MATCH_CONFIDENCE, EXTENSION_MAX_CONFIDENCE)
                results.append(
                    FrameworkPattern(
                        framework=framework,
                        category=category_map.get(framework, "other"),
                        confidence=confidence,
                        evidence={"file_count": count},
                    )
                )

        return results

    def detect_ast_level(self, nodes: ASTNodeList) -> list[FrameworkPattern]:
        """
        AST 级检测

        通过 AST 节点的注解、装饰器、命名模式检测框架。
        检测逻辑完全委托给注册表 registry.detect_by_ast。

        Args:
            nodes: AST 节点列表

        Returns:
            框架检测结果列表
        """
        return self.registry.detect_by_ast(nodes)
