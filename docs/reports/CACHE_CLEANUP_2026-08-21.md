# 项目可再生缓存清理报告

- 日期：2026-08-21
- 项目：Bedding Order Parser 源码归档
- 操作：删除可再生缓存和未完成下载残片
- 结论：完成

## 清理范围

本轮只删除经只读检查确认可再生、且不属于正式业务数据的内容：

- 项目及 `.venv` 下的 `__pycache__`、`.pytest_cache`、`.mypy_cache`、
  `.ruff_cache`、`.hypothesis`；
- 对应 `.pyc`/`.pyo` Python 字节码缓存；
- Hugging Face BGE-M3 下载留下的一个 `*.incomplete` 未完成分片；
- 空的 Hugging Face Xet 日志目录和空锁目录；
- 空的桌面程序 `cache` 目录。

删除统计：

- 缓存目录：459 个；
- 缓存文件：3,221 个；
- Python 缓存：73,491,577 字节；
- BGE-M3 未完成下载分片：402,411,069 字节；
- 合计释放：475,902,646 字节，约 453.86 MiB。

以上删除为直接删除，未进入回收站；内容均可由 Python 或下载工具重新生成。

## 明确保留

以下内容是程序运行需要的正式资源，本轮未删除：

- `.venv` Python 环境和已安装依赖；
- BGE-M3 完整模型 revision
  `5617a9f61b028005a4858fdac845db406aefb181`；
- `data/input`、`data/reference`、`data/golden` 业务与参考资料；
- `material_master.sqlite3` 和物料 JSONL；
- `materials_all.faiss`、`duvet_cover.faiss`、两份映射和向量清单；
- 桌面配置 `app_config.json`；
- 源码、测试、文档和既有报告。

## 清理后验证

- 项目缓存目录剩余：0；
- `.pyc`/`.pyo` 剩余：0；
- `data/output` 临时项剩余：0；
- Hugging Face `*.incomplete`/临时分片剩余：0；
- BGE-M3 固定 revision：存在；
- 桌面完整资源验证：`validated=True`；
- 模型名称：`BAAI/bge-m3`；
- 向量维度：1024；
- SQLite、FAISS、映射、清单和桌面配置均存在。

本轮没有调用 BGE-M3 编码、FAISS 查询、真实 PI、LLM API 或 ERP，也没有修改
业务逻辑和固定 20 字段合同。清理后未运行 pytest；本轮风险由完整资源哈希/版本
校验覆盖。

## Git 状态

当前目录没有 `.git`，不是可用的 Git 工作区，因此无法取得 HEAD、分支、
`git status` 或创建提交。
