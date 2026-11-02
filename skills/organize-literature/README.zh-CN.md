# 文献整理 organize-literature

[English](README.md) · [完整使用规则](SKILL.md)

将本地下载的文献整理成分类目录、规范文件名和 Excel 总账。可单独使用，也可作为 [distill-research-corpus](https://github.com/zz11ss11zz/distill-research-corpus) 的文献整理子 Skill。

![文献整理流程示意图](docs/workflow.svg)

## 默认目录与命名

优先采用用户指定的源目录和目的目录。未指定时，以当前项目（没有项目时为当前工作目录）为源，在其下生成：

```text
literature/
├── paper/      # 期刊 - 年份 - 标题.pdf
├── patent/     # 公开号 - 年份.pdf（也支持显式启用的专利 Markdown）
├── thesis/     # 学校 - 年份 - 标题.pdf
├── literature-ledger.xlsx
└── _organization_manifest.json
```

总账字段：分类、标题、作者、年份、期刊或学校、DOI、专利号、相对文件路径、SHA-256、原始路径。支持筛选、冻结首行、增量保留已有记录。源文件默认保留，不会自动删除；扫描时排除整理目的目录。

## 安装与使用

需要 Python 3.11+。克隆本仓库后运行 `python -m pip install -r requirements.txt`，再将仓库放入 Skill 目录，例如 `~/.codex/skills/organize-literature`。独立版与蒸馏集成版择一安装。

可以直接说：

> 用 $organize-literature 整理当前项目的文献，按 paper、patent、thesis 分类重命名，并生成 Excel 总账。

> 将指定下载目录的文献整理到指定的 literature 目录，先检查分类与重名冲突。

命令行（将 `<skill>` 换成安装目录的绝对路径）：

```sh
python <skill>/scripts/organize_academic_pdfs.py --root . --no-crossref
# 核对预览后执行：
python <skill>/scripts/organize_academic_pdfs.py --root . --no-crossref --apply
```

指定目录时使用 `--source <下载目录> --output <整理目的目录>`；指定核实过的元数据可使用 `--overrides <metadata.json>`，格式见[覆盖记录示例](references/metadata-overrides.md)。源文献应位于目的目录之外。`--no-crossref` 为离线模式，去掉后可按 DOI 查询 Crossref；缺少分类依据时保留待核，不编造信息。


## 补充材料 SI

SI 与正文一起放在 `paper/`，文件名前加 `SI -`：

```text
paper/
├── Nature - 2024 - Article title.pdf
├── SI - Nature - 2024 - Article title - 01.pdf
└── SI - Nature - 2024 - Article title - 02.xlsx
```

单份附件可以不编号；多份附件按 01、02 等区分，增量整理保留已登记的文件名。保留 PDF、Excel、ZIP 等原格式，ZIP 只复制、不解压。正文与 SI 即使 DOI 相同也分别保留；仅同一正文、相同格式且字节完全相同的 SI 副本可去重。

总账增加“文献类型”和“关联正文”，区分正文与补充材料。唯一 DOI 匹配可关联当前批次的正文路径；正文尚未收集时可登记已核实的正文 DOI，或通过 `related_paper` 指定关联。关联不明、元数据不足时保留待核。文件名只是识别线索，执行前仍需核实。未标记的附件可在元数据覆盖记录中设置 `supplementary: true`；误识别可设置为 `false`。不会仅因扩展名为 Excel 或 ZIP 就将普通文件收入文献库。

旧版十列总账会追加这两列并保留已有记录；源文件及旧总账不删除。

## 边界与验证

默认复制并保留原文件；只有明确要求时才删除精确重复项。同名不同内容、元数据未解决会阻止执行。Excel 应在更新前关闭；整批复制和台账写入不是单一事务，中断时须核对部分完成项。增量保留的总账行不会随文件缺失自动删除。

执行 `python -B -m unittest discover -s scripts -p "test_*.py" -v` 运行离线模拟测试。测试覆盖预览、分类命名、冲突保护、重复入库、默认目录和 Excel 增量保留，不代表真实扫描件或在线元数据准确率。

此项目由作者本地自建的两个 Skill 合并而来，不包含真实文献或个人项目资料。尚未选定开源许可证；公开可见不等于授予开源许可。
