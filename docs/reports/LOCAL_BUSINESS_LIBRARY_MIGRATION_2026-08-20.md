# 本地业务资料库迁移与路径配置报告

日期：2026-08-20

模式：离线实现
目标：将用户提供的床品订单资料 ZIP 安全迁入当前项目本地 `data` 库，移除运行脚本中的旧项目绝对路径，并生成可重复使用的导入和桌面配置入口。

## 1. 基线与工作区

- 当前实际项目：`D:\AI lianxi\床品Excel解析`
- 当前目录没有 `.git/`；无法现场核验分支、HEAD、Git 作者、status 或 diff。
- `SOURCE_PACKAGE_MANIFEST.md` 声明归档分支为 `master`、归档提交为 `a5c9056dda6e96d18a31c81873ff753d8acfc1be`，但本轮不能独立验证该声明。
- 用户提供 ZIP 的 SHA-256：`2f641df7fd53b53170ddfa83634b691e2b65b932ed135e1041e050964af771d2`。
- ZIP 原件只读检查与导入完成后，SHA-256 保持一致。

## 2. ZIP 资料审计

ZIP 共包含21个文件（不含目录项）：

- 12份实际 PI/订单 Excel；
- 1份系统下单语言对照 Excel；
- 1份已知20字段解析结果 JSON；
- 1份被套下单语言参考 Excel；
- `material_info.csv` 物料主数据；
- `PI单提取规则.xlsx`；
- `款式表_structured.xlsx`；
- `cover_res_template.xlsx`；
- 2份本地说明 DOCX。

物料 CSV 现场统计：

- 数据行：29,127；
- 空物料编码：0；
- 重复物料编码组：0；
- 名称中符合被套关键词的记录：29,083。

参考解析 JSON 已现场验证为3条记录，字段名称与项目固定20字段合同一致；本轮未把真实业务内容写入报告。

订单样例包含多种复杂结构：PI/ERP 双 Sheet、PI/PI-update 多版本、合并单元格、公式、极宽格式化区域和多个对照 Sheet，适合作为本地回归资料。未调用外部服务解析这些真实 PI。

## 3. 本地资料映射

新增 `packaging/import_business_library.ps1`，只允许把已知业务文件映射到配置的数据目录：

| 类型 | 导入位置 | 文件数 |
|---|---|---:|
| PI/订单样例 | `data/input/pi/` | 12 |
| 对照结果/系统下单语言 | `data/golden/` | 2 |
| 规则、款式、物料CSV、模板、参考表 | `data/reference/` | 5 |
| 本地说明文档 | `data/reference/docs/` | 2 |

导入安全边界：

- 不修改或删除 ZIP 原件；
- 只识别固定文件名和固定对照资料目录；
- 使用文件名落盘，不接受 ZIP 内任意相对路径，防止目录穿越；
- 所有目标和临时目录必须解析在指定 `DataDir` 以内；
- 默认拒绝覆盖已有文件，只有显式 `-Force` 才允许替换；
- 导入先写入 `data` 下的临时 staging，再移动到正式位置；
- 导入结束清理 staging。

现场结果：21个导入文件逐一与 ZIP entry 做 SHA-256 对比，`21 checked / 0 mismatches`。

真实业务资料继续受现有 `.gitignore` 排除，不进入源码提交范围。

## 4. 代码与配置修改

### 4.1 新增导入脚本

`packaging/import_business_library.ps1`

- 支持 `ArchivePath`、`ProjectRoot`、`DataDir` 和显式 `Force`；
- 默认项目根由脚本自身位置计算，不绑定某台电脑；
- 建立固定、安全、可复用的本地资料映射；
- 输出归档哈希、数据目录、导入数量和分类计数。

### 4.2 桌面配置脚本

`packaging/initialize_desktop_config.ps1`

- 新增可显式指定的 `DataDir`；
- 新增可测试的 `ConfigPath`；
- 默认项目根继续从脚本位置计算；
- 校验项目根必须包含 `pyproject.toml`；
- 已有配置默认拒绝覆盖，替换需要 `-Force`；
- 配置先写临时文件再移动到正式位置；
- 默认模型缓存从当前用户目录计算，不再依赖旧项目地址。

本轮已生成当前用户桌面配置：

`%LOCALAPPDATA%\BeddingOrderParser\config\app_config.json`

其中 `data_dir`、规则、款式、SQLite 物料库和待生成的向量索引均指向当前项目的 `data`。

### 4.3 本地开发快捷方式

`packaging/create_local_desktop_shortcut.ps1`

- 删除 `D:\AI-Learning\Projects\bedding-order-parser` 旧绝对默认值；
- 默认从脚本所在目录推导当前项目根；
- 本轮没有创建或覆盖用户桌面快捷方式。

### 4.4 文档与测试

- `README.md` 增加自己的业务资料库导入、映射和外置 `DataDir` 使用方法；
- `tests/desktop/test_packaging_contract.py` 将新脚本纳入打包资源合同，并断言本地设置脚本不再固定旧归档项目路径。

未修改20字段合同、五类结果角色、Standard/AI Enhanced 业务逻辑、字典算法、物料评分权重、AI Prompt、Provider、Revision 或 ERP 边界。

## 5. 本地物料库构建

本轮使用已导入的 `data/reference/material_info.csv` 执行现有确定性 material-store builder：

- SQLite：`data/output/material_store/material_master.sqlite3`；
- JSONL：`data/output/material_store/material_documents.jsonl`；
- Manifest：`data/output/material_store/material_store_manifest.json`；
- SQLite 记录：29,127；
- JSONL 记录：29,127；
- Manifest 源 SHA-256 与当前 CSV：一致。

字典加载验证：

- 提取规则行：35；
- 面料规则行：75；
- 款式规则行：105。

这些步骤没有加载 BGE-M3，没有导入 FAISS，也没有调用网络。

## 6. 测试与验证

### 6.1 PowerShell 与静态检查

- 三个本地设置脚本 PowerShell AST 解析：`0 errors`；
- `src/` 与 `tests/` 共176个 Python 文件 AST 解析：`0 errors`；
- 改动文件尾随空白扫描：无命中；
- `packaging/`、`src/`、`tests/`、`README.md` 旧项目绝对路径扫描：无命中；
- 改动文件密钥/Authorization 模式扫描：无命中；
- 导入和 pytest 临时目录残留：0。

### 6.2 定向 pytest

第一次命令使用系统 pytest 默认临时目录，结果为：

`7 passed / 5 setup errors`

5个错误均由 `C:\Users\J\AppData\Local\Temp\pytest-of-J` 无访问权限导致，发生在 `tmp_path` fixture setup，未进入对应测试代码，不是断言失败。

随后把 `--basetemp` 显式设到已忽略的 `data/output/pytest-temp-local-library`，重跑：

`12 passed in 1.33s`

测试临时目录已核验位于 `data/output` 并在运行后清理。

### 6.3 行为验证

- 首次真实资料导入：21个文件成功；
- 导入文件与 ZIP entry 哈希：21/21一致；
- 无 `-Force` 重复导入：正确拒绝覆盖；
- 桌面配置实际写入：成功；
- 配置中的规则、款式和 SQLite 路径：存在；
- Material store：29,127 SQLite / 29,127 JSONL；
- ZIP 原件最终哈希：保持不变。

## 7. 未执行与剩余条件

按项目安全规则，本轮没有得到“加载 BGE-M3 和构建/调用 FAISS”的明确授权，因此没有执行：

- BGE-M3 模型下载或加载；
- FAISS 索引构建；
- 向量检索或真实订单物料匹配；
- 真实 PI 解析；
- Ark/LLM 或任何外部 HTTP；
- 完整 pytest；
- Desktop/浏览器启动；
- PyInstaller 打包；
- 快捷方式创建。

当前桌面资源检查仍会明确报告以下缺失项：

- `duvet_cover.faiss`；
- `duvet_cover_mapping.jsonl`；
- `vector_index_manifest.json`；
- BGE-M3 本地模型缓存。

因此，本轮完成的是“自己的资料库导入、路径迁移、字典可读和 SQLite 物料库就绪”，不是完整物料匹配和桌面应用最终验收。下一 Gate 必须在用户明确授权模型来源、BGE-M3 加载和 FAISS 构建范围后执行。

## 8. 最终文件与工作区

生产/脚本/测试/文档改动：

1. `packaging/import_business_library.ps1`（新增）
2. `packaging/initialize_desktop_config.ps1`
3. `packaging/create_local_desktop_shortcut.ps1`
4. `tests/desktop/test_packaging_contract.py`
5. `README.md`
6. `docs/reports/LOCAL_BUSINESS_LIBRARY_MIGRATION_2026-08-20.md`（本报告）

本地忽略数据：

- `data/input/pi/`、`data/reference/`、`data/golden/` 中的21个导入资料；
- `data/output/material_store/` 中的3个确定性物料库产物。

用户级配置：

- `%LOCALAPPDATA%\BeddingOrderParser\config\app_config.json`。

Git：当前源码包没有 `.git`，未暂存、未提交、未 push，无法运行 `git diff --check` 或核验最终 HEAD。
