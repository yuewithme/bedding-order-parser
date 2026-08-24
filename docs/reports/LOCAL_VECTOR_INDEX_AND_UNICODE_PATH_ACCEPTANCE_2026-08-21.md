# 本地向量索引与中文路径兼容验收报告

- 日期：2026-08-21
- 范围：本地 BGE-M3 模型、FAISS 物料索引、中文 Windows 路径兼容、桌面资源绑定
- 项目目录：`D:\AI lianxi\床品Excel解析`
- 结论：通过

## 1. 授权与安全边界

本轮根据用户明确的“继续”授权，执行以下本地动作：

- 安装项目锁定的本地 Python 依赖；
- 下载并固定 BGE-M3 模型 revision；
- 对已经导入的 29,127 条物料主数据生成向量；
- 构建本地 FAISS 索引并执行一次非客户真实订单查询；
- 校验桌面配置、索引、映射、SQLite 和模型缓存。

本轮没有调用 Ark 或其他 LLM API，没有上传真实 PI，没有运行真实整单 AI
解析，没有调用 ERP，也没有把候选物料编码写回业务结果。

## 2. 基线与环境

- Python：3.12.10
- `faiss-cpu`：1.14.3
- `sentence-transformers`：5.6.1
- PyTorch：2.13.0+cpu
- BGE-M3：`BAAI/bge-m3`
- 固定 revision：`5617a9f61b028005a4858fdac845db406aefb181`
- 向量维度：1024
- 计算设备：CPU
- 向量归一化：是
- FAISS 类型：`IndexFlatIP`
- 距离含义：归一化向量内积，即余弦相似度等价排序

当前目录不是 Git 仓库。`git rev-parse`、分支、HEAD 和工作区状态均无法取得，
因此不能核实来源清单中记录的历史 commit，也不能创建本轮提交。

## 3. 数据与构建结果

向量索引来源于：

- `data/output/material_store/material_master.sqlite3`
- `data/output/material_store/material_documents.jsonl`

正式构建结果：

- 全物料索引：29,127 条；
- 被套专用索引：29,085 条；
- 批大小：16；
- 构建耗时：58,269.584 秒；
- 构建过程使用临时目录，全部校验成功后才原子发布正式目录。

产物如下：

| 文件 | 条目/行数 | 大小（字节） | SHA-256 |
|---|---:|---:|---|
| `materials_all.faiss` | 29,127 | 119,304,237 | `cf0fb3efd6b45136ad692db84a7a27ca2d8b3c3f320cbe94c5a2c13831c357c4` |
| `materials_all_mapping.jsonl` | 29,127 | 19,155,307 | `33e25faa4889a20d7dd9c2dafd8a34fbd7ecd32d5b65a23baf4ae001f7a2dfa9` |
| `duvet_cover.faiss` | 29,085 | 119,132,205 | `4df856466dd5fb24363d9119863f76b66bd6c3602ffde6553b78a810dac8f043` |
| `duvet_cover_mapping.jsonl` | 29,085 | 19,129,463 | `ee31d7b09c67a2724fbe2c1f433a385b1a63865d47eaa73281dcbef18965a3c1` |

清单文件为 `data/output/material_vector_index/vector_index_manifest.json`。重新计算的
四个 SHA-256、实际文件大小、FAISS 条目数、维度和 JSONL 行数均与清单一致。

## 4. 中文路径故障与修复

第一次完整编码结束后，FAISS 在 `write_index` 阶段无法打开包含中文字符的
Windows 文件路径。该问题发生在向量已经计算完成、正式目录尚未发布时；临时
目录已清理，没有留下可被应用误读的半成品索引。

根因是 FAISS 的原生 Windows 文件路径接口不能可靠处理当前中文路径。修复方式：

1. `faiss.serialize_index` 把索引序列化到内存；
2. 使用 Python `Path.open` 把字节写入 Unicode 路径并执行 `fsync`；
3. 读取时由 Python `Path.read_bytes` 读取，再用 `faiss.deserialize_index` 恢复；
4. 构建、直接检索和混合匹配统一走同一套安全读写函数。

新增了中文目录和中文文件名的回归测试。首次针对性测试发现两个旧测试仍直接
调用 `faiss.read_index`，测试代码同步改为走统一读取函数后，相关测试 21 项通过。

## 5. 运行验收

### 本地向量查询

在 `HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1` 下，以通用测试文本执行被套
索引 Top-5 查询：

- 返回数量：5；
- 排名：1 至 5 连续；
- 分数：`0.840876`、`0.834952`、`0.831811`、`0.828755`、`0.828753`；
- 分数严格按非增序排列；
- 五条结果均成功从映射文件恢复非空物料编码。

查询只验证技术链路，未把候选编码视为业务确认结果。

### 桌面资源校验

桌面配置：`%LOCALAPPDATA%\BeddingOrderParser\config\app_config.json`。

- 启动轻量检查：7 类必要资源全部存在；
- 完整检查：SQLite、被套 FAISS、映射文件的哈希与向量清单一致；
- 模型名称：`BAAI/bge-m3`；
- 模型 revision：固定 revision 存在；
- 向量维度：1024；
- 最终状态：`validated=True`。

## 6. 测试与静态检查

最终定向测试命令覆盖 `tests/materials`、桌面资源、打包合同和桌面运行组合：

- 结果：94 passed；
- 耗时：13.53 秒；
- pytest 缓存被禁用；
- `basetemp` 位于 `data/output` 的受控目录，测试后已验证路径并删除；
- 最终未发现 pytest/temp/tmp 残留目录。

其他检查：

- Python 源码静态编译：177 个文件通过；
- PowerShell 解析：`packaging/*.ps1` 零错误；
- 旧固定项目绝对路径扫描：零匹配；
- 本轮涉及文件的尾随空格扫描：零匹配；
- 本轮涉及文件的内嵌 API Key/Authorization 扫描：零匹配。

未执行完整仓库 pytest；本轮使用覆盖向量、物料和桌面资源链路的 94 项定向测试。
未执行真实 PI、真实 LLM、BGE-M3 重新下载或 ERP 验收。

## 7. 本轮代码和文档变化

- 新增 `src/bedding_order_parser/materials/faiss_io.py`；
- 修改 `vector_index.py`、`vector_search.py`、`hybrid_matcher.py`，统一使用
  Unicode-safe FAISS 读写；
- 修改 `tests/materials/test_vector_index.py`，新增中文路径回归并消除测试中的
  原生 Unicode 路径调用；
- 更新 `README.md` 的现状说明，使其与已经存在的字典、向量检索、Web 和桌面能力一致；
- 生成本报告。

## 8. 仍需注意的业务边界

- BGE-M3/FAISS 的职责是“召回语义接近的候选”，不是自动证明编码正确；
- 最终候选还需结构化字段比较、硬冲突处理和人工复核；
- 当前不应自动写回 ERP；
- `ai_enhanced` 的代码存在，但没有真实 Provider 验收，不代表当前机器已获得
  可用的外部 AI 服务；
- 本项目不是传统 OCR 系统，单元格内容由 `openpyxl` 读取；图片中的文字不会被
  这条标准解析链路自动识别。
