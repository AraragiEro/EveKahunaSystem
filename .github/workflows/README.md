# GitHub Actions 自动同步配置说明

## 概述

此工作流用于自动将私有仓库的社区版代码同步到公开仓库，自动排除企业版相关文件。

## 配置步骤

### 1. 创建 Personal Access Token (PAT)

1. 登录 GitHub，进入 **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. 点击 **"Generate new token (classic)"**
3. 配置 Token：
   - **Note**: `Public Repo Sync Token`
   - **Expiration**: 根据需要选择（建议 90 天或 No expiration）
   - **Scopes**: **必须勾选 `repo`（完整仓库权限）**
     - ✅ **`repo`** - 完整仓库访问权限（包括私有仓库）**（必须）**
     - ✅ `workflow` - 更新 GitHub Actions 工作流（可选）
4. 点击 **"Generate token"**
5. **重要**: 复制生成的 token（只显示一次，请妥善保存）

**⚠️ 重要提示**：
- **必须使用 Classic PAT（不是 Fine-grained tokens）**
- Token 必须有 `repo` 权限才能推送到仓库
- `repo` 权限包括：
  - `repo:status` - 访问提交状态
  - `repo_deployment` - 访问部署状态
  - `public_repo` - 访问公共仓库
  - `repo:invite` - 访问仓库邀请
  - `security_events` - 访问安全事件
- Token 必须对**目标公开仓库**有写入权限
- 如果遇到 403 错误，请重新创建 Token 并确保勾选 `repo` 权限

### 2. 在私有仓库中添加 Secret

1. 进入私有仓库的 **Settings** → **Secrets and variables** → **Actions**
2. 点击 **"New repository secret"**
3. 添加 Secret：
   - **Name**: `PUBLIC_REPO_TOKEN`
   - **Value**: 粘贴刚才创建的 PAT
4. 点击 **"Add secret"**

### 3. 修改公开仓库地址和分支

编辑 `.github/workflows/sync-to-public.yml` 文件：

1. **修改仓库地址**（如果需要）：
   - 找到 `git remote add public` 行
   - 将 `AraragiEro/EveKahunaSystem` 替换为你的实际公开仓库地址（格式：`用户名/仓库名`）

2. **确认分支名称**：
   - 工作流已配置为推送到 `master` 分支
   - 如果公开仓库使用其他分支名，需要修改 `git push public HEAD:master` 中的分支名

### 4. 提交并测试

1. 提交工作流文件：
```bash
git add .github/workflows/sync-to-public.yml
git commit -m "feat: 添加自动同步到公开仓库的工作流"
git push origin main
```

2. 在 GitHub 上查看 Actions：
   - 进入私有仓库的 **"Actions"** 标签页
   - 查看工作流执行状态和日志

## 工作流说明

### 触发条件

- **自动触发**: 当代码推送到 `main` 分支时自动触发
- **手动触发**: 在 GitHub Actions 页面可以手动触发（workflow_dispatch）

### 排除的文件

以下文件/目录不会被同步到公开仓库：
- `src_v2/enterprise/` - 企业版后端代码
- `src_v2/frontend/src/views/enterprise/` - 企业版前端页面
- `src_v2/frontend/src/components/enterprise/` - 企业版前端组件
- `src_v2/frontend/src/router/enterprise.ts` - 企业版路由配置
- `config.enterprise.toml` - 企业版配置文件
- `.env.enterprise` - 企业版环境变量

### 工作流程

1. **检出代码**: 从私有仓库检出最新代码
2. **清理文件**: 删除所有企业版相关文件和目录
3. **提交变更**: 如果有变更，自动提交（使用 `[skip ci]` 避免循环触发）
4. **推送到公开仓库**: 使用 PAT 推送到公开仓库的 main 分支
5. **清理**: 移除临时远程仓库配置

## 故障排查

### 问题 1: 同步失败，提示 "PUBLIC_REPO_TOKEN 未设置"

**解决方案**: 
- 检查是否在仓库 Secrets 中添加了 `PUBLIC_REPO_TOKEN`
- 确认 Secret 名称拼写正确（区分大小写）

### 问题 2: 推送失败，提示权限不足（403 错误）

**错误信息**: `Permission denied to github-actions[bot]` 或 `The requested URL returned error: 403`

**解决方案**:
1. **检查 PAT 权限**:
   - 确保 PAT 具有 `repo` 权限（完整仓库权限）
   - 如果使用 Fine-grained tokens，确保有目标仓库的写入权限
   
2. **验证 Token 有效性**:
   - 检查 Token 是否过期
   - 重新生成 Token 并更新 Secret
   
3. **检查仓库访问权限**:
   - 确认目标公开仓库存在且可访问
   - 确认 Token 所属账户有访问该仓库的权限
   - 如果是组织仓库，确认 Token 有组织权限
   
4. **测试 Token**:
   ```bash
   # 在本地测试 Token 是否有效
   curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
   ```

5. **使用 Fine-grained tokens 时**:
   - 确保在 Token 设置中明确授予目标仓库的访问权限
   - 选择 "Repository access" → "Only select repositories" → 选择目标仓库
   - 授予 "Contents" 和 "Metadata" 权限（至少需要写入权限）

### 问题 3: 分支名称不匹配

**解决方案**:
- 工作流已配置为推送到 `master` 分支（公开仓库）
- 如果公开仓库使用其他分支名，修改工作流中的 `git push public HEAD:master` 为对应的分支名
- 私有仓库使用 `main` 分支，公开仓库使用 `master` 分支

### 问题 4: 企业版文件被同步

**解决方案**:
- 检查 `.gitignore` 是否正确配置
- 确认工作流的 `paths-ignore` 配置正确
- 检查企业版文件是否在正确的目录下

## 安全注意事项

1. **Token 安全**: 
   - PAT 只存储在 GitHub Secrets 中，不要提交到代码仓库
   - 定期轮换 PAT（建议每 90 天）

2. **分支保护**:
   - 在公开仓库设置分支保护规则
   - 防止直接推送到受保护的分支

3. **权限最小化**:
   - PAT 只需要 `repo` 权限，不需要其他权限

## 手动触发同步

如果需要手动触发同步：

1. 进入私有仓库的 **Actions** 标签页
2. 选择 **"Sync to Public Repository"** 工作流
3. 点击 **"Run workflow"** 按钮
4. 选择分支（通常是 `main`）
5. 点击 **"Run workflow"** 确认

## 监控和通知

工作流执行后，可以在以下位置查看结果：

- **Actions 标签页**: 查看工作流执行历史和日志
- **公开仓库**: 检查代码是否已同步
- **工作流日志**: 查看详细的执行步骤和错误信息

## 更新工作流

如果需要修改工作流配置：

1. 编辑 `.github/workflows/sync-to-public.yml`
2. 提交更改
3. 工作流会在下次触发时使用新配置

---

**注意**: 首次配置后，建议先手动触发一次工作流，确认配置正确后再依赖自动触发。

