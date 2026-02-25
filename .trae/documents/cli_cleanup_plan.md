# CLI 清理与注册计划

## 一、任务概述

1. 删除历史 CLI 文件 `main.py`
2. 在 `cli/__init__.py` 定义新的 CLI 入口函数
3. 在 `pyproject.toml` 注册命令

## 二、具体修改

### 2.1 删除历史文件

**删除文件：**
- `src/duckkb/main.py` - 已废弃的旧 CLI 入口

### 2.2 更新 `cli/__init__.py`

```python
"""CLI 工具模块。

提供基于 typer 的命令行工具实现，
将知识库能力暴露为 CLI 命令。
"""

from duckkb.cli.duck_typer import DuckTyper

__all__ = ["DuckTyper", "app", "main"]

app = DuckTyper()


def main() -> None:
    """CLI 入口函数。

    用于 pyproject.toml 中的 project.scripts 注册。
    """
    app()
```

### 2.3 更新 `pyproject.toml`

```toml
[project.scripts]
duckkb = "duckkb.cli:main"
```

## 三、使用方式

```bash
# 安装后可直接使用
duckkb --kb-path /path/to/kb serve
duckkb -k /path/to/kb version
duckkb version
```

## 四、实现步骤

| 步骤 | 任务 |
|------|------|
| 1 | 删除 `src/duckkb/main.py` |
| 2 | 更新 `cli/__init__.py` 添加 `app` 和 `main()` |
| 3 | 更新 `pyproject.toml` 添加 `[project.scripts]` |
| 4 | 运行 ruff 格式化 |
