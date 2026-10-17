# AGENTS 说明
本文件用于约束本仓库的协作规范与输出偏好，适用于所有新增或修改的工作。

## 项目概况
- **项目类型**: Quart (Python) + Vue3 Web 应用
- **用途**: EVE Online 工业规划与资产管理系统
- **Python 版本**: 3.13+
- **包管理**: uv (推荐) 或 pip

## 基本规则
- 语言优先中文，除非用户明确要求英文
- 注意中文输出不要输出乱码
- 遵循现有代码风格与目录结构，减少无关重构
- 修改范围以任务需求为边界，不做"顺手优化"
- 保持可读性，必要时补充简短注释


## 修改检查规范

### 静态检查要求
**所有代码修改必须进行静态检查后才能提交：**

1. **Python 代码**：
   ```powershell
   # 语法检查
   python -m py_compile <file>
   
   # 或使用 ruff（推荐）
   ruff check <file>
   
   # 类型检查（可选）
   mypy <file>
   ```

2. **前端代码 (Vue/TypeScript)**：
   ```powershell
   cd src_v2/frontend
   
   # TypeScript 类型检查
   npx vue-tsc --noEmit
   
   # 或构建检查
   npm run build-only
   ```

3. **检查清单**：
   - [ ] 语法错误（SyntaxError、编译错误）
   - [ ] 类型错误（TypeScript 类型不匹配）
   - [ ] 括号/引号匹配问题
   - [ ] 导入语句是否正确

**严禁在未经静态检查的情况下直接提交代码。**

## 构建/测试/运行命令

### 依赖安装
```powershell
# 使用 uv (推荐)
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 运行服务器
```powershell
# 开发模式
python run_server.py --dev --host 0.0.0.0 --port 9527

# 生产模式
python run_server.py --prod --host 0.0.0.0 --port 9527
```

### 测试命令
```powershell
# 运行所有测试
pytest

# 运行单个测试文件
pytest tests/test_connect_manager.py

# 运行单个测试类
pytest tests/test_connect_manager.py::TestPostgreDatabaseManager

# 运行单个测试方法
pytest tests/test_connect_manager.py::TestPostgreDatabaseManager::test_init

# 运行集成测试 (需要环境变量)
$env:POSTGRES_TEST_ENABLED=1; pytest tests/test_connect_manager.py -v

# 使用 asyncio 模式
pytest --asyncio-mode=auto
```

### 前端开发 (src_v2/frontend)
```powershell
cd src_v2/frontend

# 安装依赖
npm install

# 开发服务器
npm run dev

# 构建
npm run build
```

## 代码风格指南

### Python 规范
1. **导入顺序**:
   - 标准库导入 (os, sys, datetime等)
   - 空行
   - 第三方库 (quart, sqlalchemy等)
   - 空行
   - 本地/项目导入 (src_v2.*)

2. **类型注解**: 鼓励使用类型注解，特别是函数参数和返回值

3. **命名规范**:
   - 类名: `PascalCase` (如 `PostgreDatabaseManager`)
   - 函数/方法: `snake_case` (如 `get_session`)
   - 常量: `UPPER_SNAKE_CASE`
   - 私有方法/属性: `_leading_underscore`

4. **异步代码**:
   - 使用 `async`/`await` 模式
   - 数据库操作使用 SQLAlchemy async API
   - 测试使用 `pytest.mark.asyncio`

5. **错误处理**:
   - 使用 try/except 捕获具体异常
   - 记录日志时使用 `logger.exception` 或 `logger.error`
   - 自定义异常继承 `KahunaException`

6. **日志记录**:
   - 使用 `from src_v2.core.log import logger`
   - 使用 f-string 格式化: `logger.info(f"消息: {variable}")`

### Quart API 规范
- 以 Quart 约定为准
- 可直接返回 dict 作为响应体
- 需要自定义状态码或 headers 时使用 `jsonify`
- 错误处理要统一为结构化返回并记录日志
- 使用 Blueprint 组织路由
- 使用 `@auth_required` 装饰器保护需要认证的端点
- API 响应使用 dataclass 定义模型

### 数据库操作规范
- PostgreSQL 操作: `src_v2/core/database/kahuna_database_utils_v2.py`
- Neo4j 操作: `src_v2/core/database/neo4j_utils.py`
- 使用 SQLAlchemy 2.0 的 async API
- 数据库模型定义在 `src_v2/core/database/model.py`

### 前端规范
- Vue3 + TypeScript + Element Plus
- 组件使用 Composition API
- API 客户端统一管理

## Commit Message 规范
- 使用中文
- 标题简短清晰，描述改动目标
- 需要列出涉及的文件与关键改动点
- 多文件协作改动请在同一条目中说明关联关系
- 格式:
  - `[类型] 简短中文描述`
  - `1. 文件A 关键改动`
  - `2. 文件B 文件C 关联改动`
- 示例:
  - `feat: 新增用户注册`
  - `1. src/user.py 增加注册入口`
  - `2. src/auth.py src/db.py 增加注册校验与存储`

## 运行与环境
- 开发环境为 Windows
- 命令以 PowerShell 可用为准
- 配置文件: `config.toml` (参考 `config.toml.example`)

## 数据库初始化
```powershell
# 更新 SDE 数据库
python update_sde.py

# 初始化 Neo4j
python init_neo4j.py
```

## 计划与任务
- 中等及以上复杂度任务需要拆分为 todos
- todo 项要可执行、可验收

## 项目结构
```
src_v2/
├── backend/          # Quart 后端 API
│   ├── api/          # API 路由 Blueprint
│   ├── app.py        # 应用入口
│   └── auth.py       # 认证相关
├── core/             # 核心功能
│   ├── config/       # 配置管理
│   ├── database/     # 数据库操作
│   ├── log/          # 日志
│   ├── permission/   # 权限管理
│   ├── picture_render/ # 图片渲染
│   ├── user/         # 用户管理
│   └── utils/        # 工具函数
├── enterprise/       # 企业版功能
├── frontend/         # Vue3 前端
│   └── src/
└── model/            # 业务模型
    └── EVE/          # EVE Online 相关
        ├── eveesi/   # ESI API
        ├── industry/ # 工业制造
        ├── market/   # 市场数据
        └── sde/      # SDE 数据库
```

## 测试规范
- 测试文件放在 `tests/` 目录
- 使用 pytest 框架
- 异步测试使用 `@pytest.mark.asyncio`
- Mock 使用 `unittest.mock` (Mock, AsyncMock, MagicMock, patch)
- 集成测试需要环境变量: `POSTGRES_TEST_ENABLED=1`, `REDIS_TEST_ENABLED=1`

## 依赖管理
- 生产依赖: `pyproject.toml` 的 `[project].dependencies`
- 开发依赖: `requirements.txt` 包含 pytest 等
- 使用 `uv` 管理虚拟环境和依赖

## Playwright 端到端测试规范

### 测试方法
使用 Playwright 进行端到端 (E2E) 测试，验证前端页面功能、样式和交互。

#### 常用测试流程
```
1. 导航到目标页面
2. 等待页面加载完成
3. 执行用户操作（点击、输入等）
4. 验证页面状态
5. 截图留存（可选）
6. 清理关闭浏览器
```

#### 测试示例
```powershell
# 1. 加载 Playwright skill
skill("playwright")

# 2. 导航到页面
skill_mcp(mcp_name="playwright", tool_name="browser_navigate", arguments='{"url":"http://localhost:5173/workflow/wf_token"}')

# 3. 等待加载
skill_mcp(mcp_name="playwright", tool_name="browser_wait_for", arguments='{"time":3}')

# 4. 执行 JavaScript 检查
skill_mcp(mcp_name="playwright", tool_name="browser_evaluate", arguments='{"function":"() => { return document.title; }"}')

# 5. 截图
skill_mcp(mcp_name="playwright", tool_name="browser_take_screenshot", arguments='{"type":"png","filename":"test-result.png"}')

# 6. 关闭浏览器
skill_mcp(mcp_name="playwright", tool_name="browser_close", arguments='{}')
```

#### 获取页面信息
```javascript
// 检查元素样式
const style = getComputedStyle(element);
return { color: style.color, background: style.background };

// 检查表格数据
const rows = document.querySelectorAll('table tbody tr');
return Array.from(rows).map(r => r.textContent);

// 检查 Vue 路由状态
const vueApp = document.querySelector('#app').__vue_app__;
const route = vueApp?.config?.globalProperties?.$route;
return { path: route?.path, name: route?.name };
```

### 临时文件路径规范

#### 默认临时目录
- **路径**: `.playwright-mcp/`
- **位置**: 项目根目录
- **用途**: 存放 Playwright 运行时生成的临时文件

#### 文件类型
| 类型 | 文件名格式 | 说明 |
|------|-----------|------|
| 页面快照 | `page-{timestamp}.yml` | 页面可访问性树快照 |
| 控制台日志 | `console-{timestamp}.log` | 浏览器控制台输出 |
| 截图 | 自定义或默认路径 | 页面截图 |

### 清理方法

#### 测试结束后清理
```powershell
# 1. 关闭浏览器
skill_mcp(mcp_name="playwright", tool_name="browser_close", arguments='{}')

# 2. 清理 Playwright 临时文件
Remove-Item -Path ".playwright-mcp\*" -Recurse -Force -ErrorAction SilentlyContinue

# 3. 清理测试截图（如有）
Remove-Item -Path "test-*.png" -Force -ErrorAction SilentlyContinue
```

#### 注意事项
- **必须关闭浏览器后再清理文件**，否则可能文件被占用
- 使用 `-ErrorAction SilentlyContinue` 避免目录不存在时报错
- 定期清理避免磁盘空间占用

### 测试检查清单
- [ ] 页面是否正确加载（无空白、无错误）
- [ ] 深色/浅色模式样式是否正确应用
- [ ] 用户交互功能是否正常（登录、提交、按钮点击）
- [ ] 数据是否正确显示（表格、列表）
- [ ] 控制台是否有错误信息
- [ ] 测试完成后是否清理临时文件
