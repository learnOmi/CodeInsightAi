"""
FrameworkDetector - 框架检测引擎

通过文件级扫描、AST 级分析、依赖级分析三个层面检测项目使用的框架和技术栈。

检测流程：
1. 文件级检测（最快，零解析成本）：通过文件路径、文件内容模式匹配
2. AST 级检测（精确）：通过注解/装饰器/命名模式识别框架角色
3. 依赖级检测（确认）：通过 package.json/pom.xml 等确认框架版本

输出：框架检测结果，写入 framework_patterns 表
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from codeinsight.parsers.base import ASTNodeList

logger = logging.getLogger(__name__)


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


class FrameworkDetector:
    """
    框架检测引擎

    支持三种检测级别：文件级、AST 级、依赖级。
    """

    FRAMEWORK_FILE_SIGNATURES = {
        "spring_boot": {
            "category": "backend",
            "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "content_patterns": ["spring-boot-starter", "org.springframework.boot"],
            "version_pattern": r"<version>([\d.]+)</version>",
        },
        "react": {
            "category": "frontend",
            "files": ["package.json"],
            "content_patterns": ['"react":', '"react-dom":'],
            "version_pattern": r'"react"\s*:\s*"([^"]+)"',
        },
        "vue": {
            "category": "frontend",
            "files": ["package.json"],
            "content_patterns": ['"vue":'],
            "version_pattern": r'"vue"\s*:\s*"([^"]+)"',
        },
        "angular": {
            "category": "frontend",
            "files": ["package.json"],
            "content_patterns": ['"@angular/core":', '"@angular/common":'],
            "version_pattern": r'"@angular/core"\s*:\s*"([^"]+)"',
        },
        "express": {
            "category": "backend",
            "files": ["package.json"],
            "content_patterns": ['"express":'],
            "version_pattern": r'"express"\s*:\s*"([^"]+)"',
        },
        "flask": {
            "category": "backend",
            "files": ["requirements.txt", "Pipfile", "pyproject.toml", "setup.py"],
            "content_patterns": ["flask", "Flask"],
            "version_pattern": r"flask[>=~]=?\s*([\d.]+)",
        },
        "fastapi": {
            "category": "backend",
            "files": ["requirements.txt", "Pipfile", "pyproject.toml", "setup.py"],
            "content_patterns": ["fastapi", "FastAPI"],
            "version_pattern": r"fastapi[>=~]=?\s*([\d.]+)",
        },
        "django": {
            "category": "backend",
            "files": ["requirements.txt", "Pipfile", "pyproject.toml", "setup.py"],
            "content_patterns": ["django", "Django"],
            "version_pattern": r"django[>=~]=?\s*([\d.]+)",
        },
        "gin": {
            "category": "backend",
            "files": ["go.mod"],
            "content_patterns": ["gin-gonic/gin"],
            "version_pattern": r"github\.com/gin-gonic/gin\s+v([\d.]+)",
        },
        "echo": {
            "category": "backend",
            "files": ["go.mod"],
            "content_patterns": ["labstack/echo"],
            "version_pattern": r"github\.com/labstack/echo\s+v([\d.]+)",
        },
        "nestjs": {
            "category": "backend",
            "files": ["package.json"],
            "content_patterns": ['"@nestjs/core":'],
            "version_pattern": r'"@nestjs/core"\s*:\s*"([^"]+)"',
        },
    }

    FRAMEWORK_EXTENSION_SIGNATURES = {
        "vue": {
            "category": "frontend",
            "extensions": [".vue"],
        },
        "react": {
            "category": "frontend",
            "extensions": [".tsx", ".jsx"],
        },
        "angular": {
            "category": "frontend",
            "extensions": [".component.ts", ".module.ts"],
        },
        "java": {
            "category": "backend",
            "extensions": [".java"],
        },
        "python": {
            "category": "backend",
            "extensions": [".py"],
        },
        "go": {
            "category": "backend",
            "extensions": [".go"],
        },
    }

    def __init__(self) -> None:
        pass

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

        通过文件路径和内容模式匹配检测框架。

        Args:
            repo_path: 仓库路径

        Returns:
            框架检测结果列表
        """
        results: list[FrameworkPattern] = []
        path = Path(repo_path)

        if not path.exists() or not path.is_dir():
            return results

        for framework, config in self.FRAMEWORK_FILE_SIGNATURES.items():
            confidence = 0.0
            evidence: dict[str, Any] = {}

            for file_name in config["files"]:
                file_path = path / file_name
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        for pattern in config["content_patterns"]:
                            if pattern in content:
                                confidence += 0.1
                                if "files" not in evidence:
                                    evidence["files"] = []
                                evidence["files"].append(str(file_path.relative_to(path)))

                                version_pattern = cast(str | None, config.get("version_pattern"))
                                if version_pattern:
                                    match = re.search(version_pattern, content)
                                    if match:
                                        evidence["version"] = match.group(1)

                    except Exception as exc:
                        logger.warning("读取文件失败 %s: %s", file_path, exc)

            if confidence > 0:
                results.append(
                    FrameworkPattern(
                        framework=framework,
                        category=cast(str, config["category"]),
                        confidence=min(confidence, 0.3),
                        evidence=evidence,
                    )
                )

        ext_results = self._detect_by_extensions(path)
        results.extend(ext_results)

        return results

    def _detect_by_extensions(self, repo_path: Path) -> list[FrameworkPattern]:
        """
        通过文件扩展名检测框架

        Args:
            repo_path: 仓库路径

        Returns:
            框架检测结果列表
        """
        results = []
        ext_count: dict[str, int] = {}

        for _root, _, files in repo_path.walk():
            for file in files:
                for framework, config in self.FRAMEWORK_EXTENSION_SIGNATURES.items():
                    for ext in config["extensions"]:
                        if file.endswith(ext):
                            ext_count[framework] = ext_count.get(framework, 0) + 1
                            break

        for framework, count in ext_count.items():
            if count >= 1:
                config = self.FRAMEWORK_EXTENSION_SIGNATURES[framework]
                confidence = min(count * 0.05, 0.2)
                results.append(
                    FrameworkPattern(
                        framework=framework,
                        category=cast(str, config["category"]),
                        confidence=confidence,
                        evidence={"file_count": count},
                    )
                )

        return results

    def detect_ast_level(self, nodes: ASTNodeList) -> list[FrameworkPattern]:
        """
        AST 级检测

        通过 AST 节点的注解、装饰器、命名模式检测框架。

        Args:
            nodes: AST 节点列表

        Returns:
            框架检测结果列表
        """
        results = []
        tag_counts: dict[str, int] = {}
        annotation_counts: dict[str, int] = {}

        for node in nodes.nodes:
            for tag in node.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

            for annotation in node.annotations:
                ann_name = annotation.get("name", "")
                annotation_counts[ann_name] = annotation_counts.get(ann_name, 0) + 1

        framework_matches = self._match_tags_to_framework(tag_counts)
        for framework, count in framework_matches.items():
            category = self._get_framework_category(framework)
            confidence = min(count * 0.1, 0.4)
            results.append(
                FrameworkPattern(
                    framework=framework,
                    category=category,
                    confidence=confidence,
                    evidence={"tag_matches": count},
                )
            )

        annotation_matches = self._match_annotations_to_framework(annotation_counts)
        for framework, count in annotation_matches.items():
            found = False
            for result in results:
                if result.framework == framework:
                    result.confidence += min(count * 0.1, 0.2)
                    result.confidence = min(result.confidence, 1.0)
                    result.evidence["annotation_matches"] = count
                    found = True
                    break
            if not found:
                category = self._get_framework_category(framework)
                confidence = min(count * 0.1, 0.4)
                results.append(
                    FrameworkPattern(
                        framework=framework,
                        category=category,
                        confidence=confidence,
                        evidence={"annotation_matches": count},
                    )
                )

        return results

    def _match_tags_to_framework(self, tag_counts: dict[str, int]) -> dict[str, int]:
        """
        将标签匹配到框架

        Args:
            tag_counts: 标签计数

        Returns:
            框架 → 匹配数
        """
        tag_to_framework = {
            "react-component": "react",
            "react-hook": "react",
            "react-context": "react",
            "vue-component": "vue",
            "vue-composable": "vue",
            "vue-lifecycle": "vue",
            "vue-component-api": "vue",
            "http-controller": "spring_boot",
            "business-service": "spring_boot",
            "data-repository": "spring_boot",
            "spring-component": "spring_boot",
            "spring-config": "spring_boot",
            "spring-aspect": "spring_boot",
            "flask-route": "flask",
            "fastapi-route": "fastapi",
            "celery-task": "celery",
            "http-handler": "gin",
        }

        result: dict[str, int] = {}
        for tag, count in tag_counts.items():
            if tag in tag_to_framework:
                framework = tag_to_framework[tag]
                result[framework] = result.get(framework, 0) + count

        return result

    def _match_annotations_to_framework(self, annotation_counts: dict[str, int]) -> dict[str, int]:
        """
        将注解匹配到框架

        Args:
            annotation_counts: 注解计数

        Returns:
            框架 → 匹配数
        """
        annotation_to_framework = {
            "@RestController": "spring_boot",
            "@Controller": "spring_boot",
            "@Service": "spring_boot",
            "@Repository": "spring_boot",
            "@Component": "spring_boot",
            "@Configuration": "spring_boot",
            "@Autowired": "spring_boot",
            "@GetMapping": "spring_boot",
            "@PostMapping": "spring_boot",
            "@SpringBootApplication": "spring_boot",
            "@app.route": "flask",
            "@app.get": "fastapi",
            "@app.post": "fastapi",
            "@router.get": "fastapi",
            "@router.post": "fastapi",
        }

        result: dict[str, int] = {}
        for annotation, count in annotation_counts.items():
            for pattern, framework in annotation_to_framework.items():
                if annotation.startswith(pattern):
                    result[framework] = result.get(framework, 0) + count
                    break

        return result

    def _get_framework_category(self, framework: str) -> str:
        """
        获取框架类别

        Args:
            framework: 框架标识

        Returns:
            框架类别
        """
        category_map = {
            "spring_boot": "backend",
            "react": "frontend",
            "vue": "frontend",
            "angular": "frontend",
            "express": "backend",
            "flask": "backend",
            "fastapi": "backend",
            "django": "backend",
            "gin": "backend",
            "echo": "backend",
            "nestjs": "backend",
            "celery": "backend",
        }
        return category_map.get(framework, "other")
