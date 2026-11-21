# ETL编排与数据质量中心

面向数据仓库ETL作业场景，提供流水线编排、质量规则、依赖调度和回刷补偿的ETL治理平台

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 流水线定义 | `pipeline_def` | ETL流水线 | 流水线名称、处理阶段、输入源表 |
| 任务节点 | `task_node` | 处理节点 | 节点名称、所属管线、节点类型 |
| 质量规则 | `quality_rule` | 校验规则 | 规则名称、目标表、校验字段 |
| 质量执行 | `validation_run` | 校验批次 | 批次标识、目标表、校验分区 |
| 引用字典版本 | `reference_dictionary_version` | 地区字典版本 | 引用版本号、执行日期、引用列、冻结时间 |
| 字典变更台账 | `reference_dictionary_change` | 条目补录记录 | 门店代码、地区编码、派生版本号 |
| 依赖调度 | `depend_scheduler` | 调度配置 | 配置名称、目标管线、触发方式 |
| 滑动窗口 | `sliding_window` | 窗口配置 | 窗口名称、目标表、窗口字段 |
| 回刷补偿 | `rerun_compensation` | 重跑任务 | 任务名称、目标管线、重跑范围 |
| 水位追踪 | `watermark_tracker` | 水位记录 | 管线标识、分区字段、当前水位 |
| 资源池 | `resource_pool` | 计算资源 | 池名称、总核数、总内存 |
| 血缘图谱 | `lineage_graph` | 血缘边 | 源节点、目标节点、传递字段 |
| 异常捕获 | `exception_capture` | 异常记录 | 发生时间、所属管线、异常类型 |
| 模板仓库 | `template_store` | 处理模板 | 模板名称、处理类型、输入Schema |
| 分区扫描 | `partition_scan` | 扫描报告 | 报告时间、目标表、分区总数 |
| 配置迁移 | `config_migration` | 迁移任务 | 任务名称、源环境、目标环境 |
| Schema演进 | `schema_evolution` | 变更记录 | 变更时间、目标表、变更类型 |
| 回填追踪 | `backfill_tracker` | 回填进度 | 追踪ID、回填任务、当前分区 |
| 成本分析 | `cost_analysis` | 成本快照 | 快照日期、管线标识、计算时长 |
| 告警策略 | `alert_policy` | 告警规则 | 规则名称、监控对象、告警条件 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 地区引用字典版本

门店订单的地区引用完整性不再按表名读取“当前字典”，而是绑定到一个冻结的字典版本：

- `reference_dictionary_version` 持久化每个版本：执行日期、引用列、冻结时间和完整条目快照；
  新增地区条目会派生新版本（`REGION-v2` → `REGION-v3`），旧版本保留为“历史”且只读。
- 质量执行批次记录 `引用版本ID/引用版本号`，并保留 `样本行`、`坏行明细`、`取值依据`，
  坏行率的分子（未匹配行数）与分母（样本行数）都由该版本解释。
- 同一批行只允许按一个已确认版本计算；草稿/历史版本会被拒绝。
- 复查（`POST /api/quality/validation-runs/{id}/review`）只读，不改写已归档样本计数。
- 重算（`POST /api/quality/validation-runs/{id}/recompute`）另存新批次并保存使用的版本，
  原批保持不变，可与 `POST /api/quality/validation-runs/compare` 对比原坏行是否通过。

相关接口：

```text
GET  /api/quality/reference-versions
POST /api/quality/reference-versions            补录条目并派生新版本
GET  /api/quality/validation-runs/reference-summary
GET  /api/quality/validation-runs/{id}/reference-evidence
POST /api/quality/validation-runs/{id}/review
POST /api/quality/validation-runs/{id}/recompute
POST /api/quality/validation-runs/compare
POST /api/business/quality/gate                 可选 reference_version_id
```

后端回归测试：

```bash
cd backend && .venv/bin/python -m unittest discover -s tests -t . -v
```

领域：数据工程
子方向：数仓与数据湖
