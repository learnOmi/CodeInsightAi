"""
语言检测器单元测试

测试语言检测器的扩展名映射和文件类型识别功能。
"""

from pathlib import Path

from codeinsight.scanners.language_detector import LanguageDetector


class TestLanguageDetector:
    """LanguageDetector 单元测试"""

    def test_detect_python(self) -> None:
        """检测 Python 文件"""
        detector = LanguageDetector()
        assert detector.detect(Path("test.py")) == "python"
        assert detector.detect(Path("test.pyi")) == "python"

    def test_detect_javascript(self) -> None:
        """检测 JavaScript 文件"""
        detector = LanguageDetector()
        assert detector.detect(Path("test.js")) == "javascript"
        assert detector.detect(Path("test.jsx")) == "javascript"

    def test_detect_typescript(self) -> None:
        """检测 TypeScript 文件"""
        detector = LanguageDetector()
        assert detector.detect(Path("test.ts")) == "typescript"
        assert detector.detect(Path("test.tsx")) == "typescript"

    def test_detect_java(self) -> None:
        """检测 Java 文件"""
        detector = LanguageDetector()
        assert detector.detect(Path("Test.java")) == "java"

    def test_detect_go(self) -> None:
        """检测 Go 文件"""
        detector = LanguageDetector()
        assert detector.detect(Path("main.go")) == "go"

    def test_detect_rust(self) -> None:
        """检测 Rust 文件"""
        detector = LanguageDetector()
        assert detector.detect(Path("lib.rs")) == "rust"

    def test_detect_c(self) -> None:
        """检测 C 文件"""
        detector = LanguageDetector()
        assert detector.detect(Path("main.c")) == "c"
        assert detector.detect(Path("header.h")) == "c"

    def test_detect_cpp(self) -> None:
        """检测 C++ 文件"""
        detector = LanguageDetector()
        assert detector.detect(Path("main.cpp")) == "cpp"
        assert detector.detect(Path("header.hpp")) == "cpp"

    def test_detect_unknown(self) -> None:
        """检测未知文件类型"""
        detector = LanguageDetector()
        assert detector.detect(Path("test.xyz")) == "unknown"

    def test_is_supported_python(self) -> None:
        """检查 Python 文件是否支持"""
        detector = LanguageDetector()
        assert detector.is_supported(Path("test.py")) is True

    def test_is_supported_unknown(self) -> None:
        """检查未知文件类型是否不支持"""
        detector = LanguageDetector()
        assert detector.is_supported(Path("test.xyz")) is False

    def test_is_source_file_python(self) -> None:
        """检查 Python 文件是否为源代码文件"""
        detector = LanguageDetector()
        assert detector.is_source_file(Path("test.py")) is True

    def test_is_source_file_markdown(self) -> None:
        """检查 Markdown 文件是否为源代码文件"""
        detector = LanguageDetector()
        assert detector.is_source_file(Path("README.md")) is False

    def test_is_source_file_json(self) -> None:
        """检查 JSON 文件是否为源代码文件"""
        detector = LanguageDetector()
        assert detector.is_source_file(Path("config.json")) is False
