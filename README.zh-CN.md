# Research Corpus Distillation

[English](README.md) | 中文

面向科研资料库的本地优先提取引擎与 Codex Skill，使用**由各项目独立维护的材料配置**。

通用引擎负责读取文档和表格、按 SHA-256 去重、保留来源定位，并增量更新提取候选。各项目分别定义资料目录、材料识别规则、性质主题、单位、证据要求，以及已有正式数据集合的引用。

**当前状态：开发预览版（0.1.0）。** 仓库中的电池、合金和 SOFC 示例均使用合成测试数据。机器提取候选不等于已核验的科学测量结果。本仓库不包含真实论文、私有数据集、凭据或实际项目的主库指针。

## 架构

```text
通用核心（本仓库）
  scripts/                    提取、OCR、验证和缓存保留
  SKILL.md                    Codex 使用说明
  references/                 配置与输出约定
          |
          v
项目工作区
  config/research-corpus.json  材料体系、目录、识别规则和主库设置
  evidence-rules.md            科学证据验收要求
  .agents/skills/              可选的项目专属流程入口
  literature/                 获准处理的原始资料
  outputs/json/knowledge_distillation/  生成的结果
```

通用核心不预设项目目录名称或材料体系。SOFC 专用测量候选暂存工具位于 `examples/sofc/`，不属于全局通用提取核心。

## 环境要求

- Python 3.11 或更新版本；持续集成测试覆盖 3.11 和 3.12。
- `openpyxl` 和 `pypdf`，详见 `requirements.txt`。
- `PATH` 中可调用的 `rg`（ripgrep），用于枚举资料文件。隐藏文件和被忽略文件遵循 ripgrep 的默认行为，请使用明确、可见的资料目录。
- 扫描版 PDF 自动 OCR 需要 Windows PowerShell、Windows OCR 语言支持，以及 `PATH` 中可调用的 Poppler `pdftoppm`。OCR 是可选能力，跨平台测试样本未覆盖实际 OCR 执行。

## 快速开始

在仓库根目录执行：

```sh
python -m venv .venv
# Activate the environment using your shell's normal activation command.
python -m pip install -r requirements.txt
python scripts/preflight_corpus.py --root examples/battery
python scripts/run_incremental_distillation.py --root examples/battery
```

创建虚拟环境后，先按所用终端的方式激活环境，再执行后续命令。

查看 `examples/battery/outputs/json/knowledge_distillation/manifest.json` 和 `evidence_facts.json`。再次运行同一命令即可验证增量复用。生成结果已列入 Git 忽略规则。

也可以运行另外两个合成示例：

```sh
python scripts/run_incremental_distillation.py --root examples/alloy
python scripts/run_incremental_distillation.py --root examples/sofc
```

## 接入自己的项目

1. 参考示例，在项目内创建 `config/research-corpus.json`。
2. 在 `canonical_roots` 中设置相对于项目根目录、互不重叠的资料目录，只配置实际需要的类别。
3. 按目标材料体系定义化学式、数值／单位和性质主题的识别规则。示例规则仅用于演示，不是完整的化学式识别语法。
4. 编写项目专属证据要求，并测试正确匹配、易混淆内容和不应匹配的情况。
5. 先执行前置检查和目录预览，再运行增量提取：

```sh
python scripts/preflight_corpus.py --root /path/to/project
python scripts/distill_complete_knowledge_base.py --root /path/to/project --inventory-only
python scripts/run_incremental_distillation.py --root /path/to/project
```

将 `/path/to/project` 替换为实际项目路径。通过 `--config config/another-profile.json` 可以指定另一份相对于项目根目录的配置。不同资料库通常应使用不同的 `--output` 目录；只有在进行兼容的配置修订、并需要保留已有事实和处理记录时，才继续使用同一输出目录。

详细说明见[配置指南](references/project-profile.md)、[项目接入说明](docs/project-integration.md)和[输出约定](references/output-contract.md)（英文）。

## 作为 Codex Skill 使用

仓库根目录就是可安装的 Skill，包含 `SKILL.md`、`scripts/`、`references/` 和 `agents/`。可以使用 Codex 的 Skill 安装工具安装本仓库。各项目的材料配置和证据规则应保留在项目中，不要复制到全局安装目录。示例中的 `.agents/skills/material-corpus` 展示了简短的项目流程入口。

也可以不使用 Codex，直接运行 Python 脚本。建议在受版本控制的源码仓库中开发，完成测试后再更新已安装的 Skill。修改克隆仓库不会自动更新安装副本。

## 输出与证据边界

引擎生成清单、文件索引、去重映射、文档逐页文字、候选事实、数据集结构描述、表格转换结果，以及正式数据集合的哈希引用。PDF 页码和原文片段定位用于后续审计；文本文件的第 `1` 页表示其提取文本记录，并非真实 PDF 页码。

新增事实始终标为 `source_located_not_human_verified`。配置中的 `required_context` 和证据说明文件描述的是核验人员需要检查的条件；正则筛选不会自动证明这些条件已满足。已有核验记录和处理历史会被保留，但这不代表系统重新独立核验了它们。详见[证据模型与局限](docs/evidence-and-limitations.md)（英文）。

## 开发与测试

```sh
python -m pip install -r requirements-dev.txt
python -B -m unittest discover -s scripts -p "test_*.py" -v
python -B scripts/check_repository.py
```

GitHub Actions 会在 Windows 和 Ubuntu 上运行测试样本及仓库检查。分支、测试和审查约定见 [CONTRIBUTING.md](CONTRIBUTING.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)（英文）。

## 许可证

目前尚未选择开源许可证。仓库公开可见不等于授予开源许可。引入第三方代码前，应记录其许可证和来源。
