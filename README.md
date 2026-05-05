# knowleage_graph_build

从 **Markdown** 文档构建 **LlamaIndex PropertyGraph**，写入 **Neo4j**（属性图），支持多种路径抽取器、本地 JSON 快照、配置文件与后处理（实体对齐、标签规范化）。

## 功能概览

- **抽取**：`simple` / `dynamic` / `schema`（JSON 本体约束）/ `implicit`（chunk 邻接）/ `simple_implicit`
- **持久化**：直连 Neo4j，或 `--local-only --save-kg` 导出快照后再 `--load-kg` 导入
- **配置**：`config/build_neo4j_kg.json`（可从 [`config/build_neo4j_kg.example.json`](config/build_neo4j_kg.example.json) 复制）；命令行参数优先于配置文件
- **后处理**：APOC 实体对齐（精确 + 可选模糊，`rapidfuzz`）、三标签规范化；亦可单独运行 `python -m neo4j_kg.normalize_cli`
- **补充**：[`test/ontology_ttl_to_neo4j_example.py`](test/ontology_ttl_to_neo4j_example.py) 将 Turtle 本体导入 Neo4j（与 LlamaIndex 文档图独立）

## 环境要求

- **Python 3.10+**（推荐 **3.12**，与当前 LlamaIndex 类型注解兼容）
- **Neo4j 5+**（图存储与部分 Cypher；实体对齐等步骤需要 **APOC**）
- **OpenAI API**（抽取与嵌入，`gpt-4o-mini` / `text-embedding-3-small` 等可在配置中修改）

## 安装

```bash
cd knowleage_graph_build
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

若本机 `conda` 中有专用环境 `llm`，且项目 `.venv` 会抢占 `PATH`，可用：

```bash
./scripts/llm_env_python.sh build_neo4j_kg.py --help
```

## 环境变量

在仓库根目录创建 **`.env`**（**勿提交到 Git**），例如：

```env
OPENAI_API_KEY=sk-...
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
# 可选：Neo4j 5 逻辑库名，默认 neo4j
# NEO4J_DATABASE=neo4j
```

仅做 **本地快照**（`--local-only`）且不导入 Neo4j 时，可以不配置 `NEO4J_*`。

## 快速用法

```bash
# 默认读配置 / 内置默认；处理 regulation 目录下文档（见 --markdown-root）
python build_neo4j_kg.py --all-docs

# 仅导出 JSON，不连 Neo4j（适合重复实验）
python build_neo4j_kg.py --local-only --save-kg data/graph_snapshots/run1.json --all-docs

# 从快照写入 Neo4j 并后处理
python build_neo4j_kg.py --load-kg data/graph_snapshots/run1.json --clean

# 指定 Markdown 根目录与单文件、schema 抽取器
python build_neo4j_kg.py \
  --markdown-root path/to/md_dir \
  --file doc.md \
  --kg-extractor schema \
  --schema-config neo4j_kg/schema_kg_config.example.json \
  --schema-relaxed
```

完整参数说明：

```bash
python build_neo4j_kg.py --help
```

## 配置文件

1. 复制示例：`cp config/build_neo4j_kg.example.json config/build_neo4j_kg.json`
2. 编辑 `config/build_neo4j_kg.json`（该路径已在 `.gitignore` 中）
3. 若该文件存在，启动时会自动合并；也可用 `--config /其它路径.json` 指定

Schema 抽取使用的本体示例：[`neo4j_kg/schema_kg_config.example.json`](neo4j_kg/schema_kg_config.example.json)

## 测试脚本

在配置好 `OPENAI_API_KEY` 与 conda `llm`（或等价 Python）后：

```bash
# 遍历全部 kg-extractor（simple / dynamic / schema / implicit / simple_implicit）
./scripts/test_all_extractors.sh

# 配置覆盖 + 实体相关选项烟测，并可选调用上面的抽取矩阵
./scripts/test_rag_intro_features.sh

# 仅跑 implicit、节省调用
SKIP_LLM_EXTRACTORS=1 ./scripts/test_all_extractors.sh
```

脚本默认期望演示 Markdown 位于 `data/kg_snapshots/rag_intro_test.md`。当前 `.gitignore` 忽略了整个 `data/` 目录，克隆仓库后需自备语料或调整忽略规则。

## 其它脚本

| 路径 | 说明 |
|------|------|
| `_normalize_three_labels.py` | 等价于 `python -m neo4j_kg.normalize_cli` |
| `install_neo4j_apoc.sh` / `start_neo4j_graphrag.sh` | 本地 Neo4j / APOC 辅助（按你环境选用） |

## 仓库结构（简要）

```
build_neo4j_kg.py          # CLI 入口
neo4j_kg/                  # 包：CLI、建索引、Neo4j、快照、后处理
config/                    # 构建 JSON 配置示例
scripts/                   # llm 环境封装与测试脚本
test/ontology_ttl_to_neo4j_example.py
```

## 许可证

未随仓库声明默认许可证；如需开源请自行添加 `LICENSE` 文件。
