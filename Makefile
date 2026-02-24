.PHONY: all sync format lint build clean publish publish-ci help

# 默认目标
all: build

# -----------------------------------------------------------
# 同步虚拟环境 (uv sync)
# -----------------------------------------------------------
sync:
	@echo "Syncing virtual environment..."
	uv sync
	make format

# -----------------------------------------------------------
# ruff (uv format)
# -----------------------------------------------------------
format:
	@echo "Running ruff..."
	uv run ruff format .
	uv run ruff check --fix-only .

lint:
	@echo "Running ruff (lint)..."
	uv run ruff check .

# -----------------------------------------------------------
# 构建 (build)
# -----------------------------------------------------------
build: format
	@echo "Building package (smart versioning)..."
	echo "Running uv build..."; \
	uv build; \

# -----------------------------------------------------------
# 清理构建产物
# -----------------------------------------------------------
clean:
	@echo "Cleaning up build artifacts..."
	rm -rf dist build *.egg-info
	rm -rf .venv
	rm -rf uv.lock

# -----------------------------------------------------------
# 发布 (publish) - 修复版 (更安全的版本号替换逻辑)
# -----------------------------------------------------------
publish: build
	@echo "Publishing package (Auto-Snapshot Mode)..."
	@if [ ! -f .env ]; then echo "Error: .env file not found."; exit 1; fi
	
	@echo "Cleaning old dist artifacts..."
	@rm -rf dist build *.egg-info
	
	@cp pyproject.toml pyproject.toml.bak
	
	@echo "Temporary bumping version for release..."
	@# -------------------------------------------------------------------------
	@# 修复说明：
	@# 不再使用复杂的正则替换组 (\1)，避免 Makefile 转义灾难。
	@# 逻辑：
	@# 1. 读取文件内容。
	@# 2. 提取当前 version 里的纯数字部分 (去除 -dev, .dev0 等)。
	@# 3. 重新构造一行完整的 "version = x.x.x.dev..." 覆盖回去。
	@# -------------------------------------------------------------------------
	@python3 -c "import re, datetime; \
	t = datetime.datetime.now().strftime('%Y%m%d%H%M%S'); \
	c = open('pyproject.toml').read(); \
	match = re.search(r'version\s*=\s*\"([^\"]+)\"', c); \
	base_ver = re.sub(r'[-_\.]?dev.*', '', match.group(1)) if match else '0.0.0'; \
	new_ver_line = f'version = \"{base_ver}.dev{t}\"'; \
	c = re.sub(r'version\s*=\s*\"[^\"]+\"', new_ver_line, c); \
	open('pyproject.toml','w').write(c)"
	
	@set -e; \
	trap 'mv pyproject.toml.bak pyproject.toml && echo "Restored pyproject.toml"' EXIT; \
	echo "Running uv build..."; \
	uv build; \
	echo "Running uv publish..."; \
	set -a; source .env; set +a; \
	uv publish \
		--index "y2l" \
		--username "$$UV_PUBLISH_USERNAME" \
		--password "$$UV_PUBLISH_PASSWORD"

# -----------------------------------------------------------
# 发布 (publish-ci) - CI 模式
# -----------------------------------------------------------
publish-ci: build
	@echo "Publishing package (CI Mode)..."
	@if [ -z "$${UV_PUBLISH_USERNAME}" ] || [ -z "$${UV_PUBLISH_PASSWORD}" ]; then \
		echo "Error: UV_PUBLISH_USERNAME or UV_PUBLISH_PASSWORD not set in CI environment."; \
		exit 1; \
	fi
	uv publish \
		--index "y2l" \
		--username "$$UV_PUBLISH_USERNAME" \
		--password "$$UV_PUBLISH_PASSWORD"

# ==============================================================================
# 帮助 (Help) - 优化版
# ==============================================================================

help:
	@echo ""
	@echo "Usage:  make [command]"
	@echo ""
	@echo "\033[33m开发与构建 (Development):\033[0m"
	@echo "  \033[36mmake sync\033[0m          同步虚拟环境 (uv sync)"
	@echo "  \033[36mmake build\033[0m         构建 Python 包 (自动计算版本号)"
	@echo "  \033[36mmake clean\033[0m         清理构建产物和环境"
	@echo ""
	@echo "\033[33m发布 (Publishing):\033[0m"
	@echo "  \033[36mmake publish\033[0m       发布到私有仓库 (读取本地 .env)"
	@echo "  \033[36mmake publish-ci\033[0m    发布到私有仓库 (CI 环境专用)"
	@echo ""
