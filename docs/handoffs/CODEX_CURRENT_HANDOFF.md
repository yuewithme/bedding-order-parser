# Codex 当前交接文档

本文件是 Bedding Order Parser 新任务的低上下文入口。历史 Gate 细节以 `docs/reports/` 和 `docs/handoffs/archive/` 为准；旧报告中的旧绝对路径只表示当时环境，不是当前运行路径。

## 1. 当前项目

- 项目：床品订单智能解析与物料匹配系统（Bedding Order Parser）。
- 包名：`bedding_order_parser`。
- 当前目录：`D:\AI lianxi\床品Excel解析`。
- 分支：`master`。
- 正式本地导入基线：`c311212a071841ea521803c3d52a7cfec4f80c5f`。
- 当前作者：`yuewithme <430714704@qq.com>`。
- 当前仓库无 remote；未经用户明确授权，不 push、不 tag。

开始任务先读取根目录 `AGENTS.md`、当前任务直接相关的合同/报告，并执行：

```powershell
git rev-parse HEAD
git branch --show-current
git status --short
```

## 2. 系统现在怎么工作

系统不是单纯 RAG，也不是对 Excel 做图片 OCR。主链路先用 `openpyxl` 在本地读取工作簿结构、单元格、合并区域和订单行，然后按所选模式解析业务字段：

- `standard`：Python 确定性规则完成解析、诊断和字典验证，默认不调用 LLM。
- `ai_enhanced`：本地预处理后，AI 解析 17 个业务字段；本地证据校验、Python shadow 对照和技术完整性检查通过后才发布。
- 物料匹配：将已规范化的订单描述用本地 BGE-M3 转成 1024 维向量，通过 FAISS 召回，再叠加规格、颜色、面料、成分、款式等结构化比较，输出候选和人工审核结论。

固定业务结果仍是 `AGENTS.md` 规定的 20 个字段。两种模式都必须发布五类核心 JSON。物料编码和相似分数只能由物料匹配层产生，系统不会自动写回 ERP。

## 3. 主要运行层

- `src/bedding_order_parser/excel/`、`extraction/`、`pipeline/`：本地 Excel 结构与确定性解析。
- `src/bedding_order_parser/ai_full_order/`、`llm/`：整单 AI、证据和可靠性边界。
- `src/bedding_order_parser/dictionaries/`：业务字典加载与验证。
- `src/bedding_order_parser/materials/`：物料库、BGE-M3、FAISS、混合匹配、审核表和评估。
- `src/bedding_order_parser/web/`：本地 Web 业务界面和 Job 编排。
- `src/bedding_order_parser/desktop/`：PyWebView 桌面入口与生命周期。
- `packaging/`：PyInstaller onedir/onefile 打包与发布核验。

## 4. 数据和安全边界

- 真实 PI、物料库、模型、索引和 Job 输出位于被 `.gitignore` 排除的本地数据目录，不得提交。
- 未经明确授权，不调用真实 LLM API，不发送真实业务内容。
- 不输出 API Key、Authorization、完整请求/响应、本机业务路径或私有思维链。
- `D:\AI-Learning\Projects\Day01` 是冻结的独立项目，不得修改、清理或提交。
- 标准模式的 AI 复核只能生成只读 Sidecar；正式五类 JSON 和 ERP 不得被它改写。

## 5. 常用验证

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest tests\materials tests\desktop -q
git diff --check
git status --short
```

真实 API、真实 PI 回归、完整 BGE-M3/FAISS 重建和完整 `pytest` 都不是默认验证步骤；只有任务明确授权并需要时才运行，并在本轮唯一报告中如实记录。
