# 床品订单智能解析与物料匹配系统

## 当前阶段

当前阶段为 Gate 1 离线基线解析器。

当前已实现基于规则的 PI Excel 解析：读取真实 PI、筛选被套商品，并输出
最终 20 字段 JSON。该阶段不接入 LLM、向量检索、物料编码匹配、ERP 对比、
API、前端、Agent 或 Docker。

## 第一业务目标

读取用户提供的复杂 Excel PI 文件，筛选 duvet cover / quilt cover /
comforter cover 等被套商品，生成最终 JSON 数组。

当前 JSON 字段结构已经由用户在 Gate 1 指定。物料编码和相似分数尚未接入
物料匹配，因此基线阶段固定输出空物料编码和 `0.0` 相似分数。

## 后续规划

1. Gate 1 基线 PI 到 JSON 解析器；
2. 字段规则补强和人工复核机制；
3. LLM 结构化抽取；
4. 物料库整理；
5. 向量检索和硬条件过滤；
6. 物料编码匹配；
7. ERP 差异对比；
8. FastAPI 和前端预览；
9. Docker 部署说明。

## 当前明确不做

- 前端；
- Agent；
- LLM；
- 向量检索；
- 物料匹配；
- ERP对比；
- Docker；
- 桌面GUI。

## 项目隔离原则

本项目与D:\AI-Learning\Projects\Day01完全独立。

不得把本项目代码直接写入企业文件整理助手。
