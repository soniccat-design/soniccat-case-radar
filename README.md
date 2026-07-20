# SONIC CAT 专业鞋案例雷达

这是一个面向专业运动鞋设计工作的自动案例库项目。GitHub Actions 每天北京时间 08:00 自动从公开来源寻找专业跑鞋、跑鞋底片和专业钉鞋案例，筛选后生成 GitHub Pages 静态网页。

Codex 只负责一次性搭建、测试和维护代码；日常任务由 GitHub Actions 中的普通 Python 脚本执行，不依赖长期服务进程。

## 项目用途

- 首页展示本轮新增案例。
- 三个分类页面长期沉淀历史案例：
  - 专业跑鞋案例
  - 专业跑鞋底片案例
  - 专业钉鞋案例
- 前端只展示案例图片、所属大类和一句 20 至 40 个中文字符的参考理由。
- 后台 `data/cases.json` 保存来源链接、来源域名、鞋款名、图片哈希、评分和抓取时间，用于去重、核验、失效处理和下架。

## 本地安装

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

如果本机只有旧版 Python，也可以先运行配置和网页生成测试；GitHub Actions 会使用 Python 3.12。

## 本地运行

验证配置：

```bash
python scripts/validate_config.py
```

生成静态网页：

```bash
python scripts/build_site.py
```

本地预览：

```bash
python -m http.server 8000 -d site
```

打开 `http://localhost:8000`。

手动执行完整日更流程：

```bash
python scripts/run_daily.py
```

## 配置文件修改方法

所有抓取任务都在 `config/tasks.yml` 中配置。

常改位置：

- `categories[].enabled`：暂停或启用分类。
- `categories[].daily_limit`：修改每日精选数量。
- `categories[].keywords_zh` / `keywords_en`：修改搜索关键词。
- `sources[].enabled`：启用或关闭某个网站来源。
- `sources[].priority`：修改来源优先级。
- `global.time_windows.primary_days`：修改近一年范围，默认 365。
- `global.time_windows.fallback_days`：修改近三年范围，默认 1095。
- `global.dedupe.category_model_window_days`：修改同分类鞋款去重周期，默认 30 天。
- `global.image`：修改图片尺寸、最长边和目标大小。
- `global.reason`：修改参考理由字数。
- `global.ai`：修改 AI 接口超时和视觉优先策略。

新增分类时，复制一个 `categories` 条目，设置唯一 `id`、中文名称、路由、关键词、每日数量和图片规则，再把需要使用的来源 `sources[].use_for` 加上该分类 id。

## GitHub Pages 开启方法

1. 将本项目推送到 GitHub 仓库。
2. 打开仓库 `Settings`。
3. 进入 `Pages`。
4. `Build and deployment` 选择 `GitHub Actions`。
5. 确认仓库 `Actions` 权限允许工作流读写内容和部署 Pages。

工作流文件是 `.github/workflows/daily-cases.yml`。

## GitHub Secrets 配置方法

AI 不是必需项。没有配置时，系统会自动使用本地规则模板生成参考理由。

如需接入兼容 OpenAI Chat Completions 的接口，在仓库 `Settings -> Secrets and variables -> Actions` 添加：

- `AI_PROVIDER`
- `AI_API_KEY`
- `AI_MODEL`
- `AI_BASE_URL`

代码不会写死密钥，也不会在日志中输出密钥。

## 定时任务说明

工作流 cron 为：

```yaml
0 0 * * *
```

这是 UTC 00:00，对应北京时间 08:00。也支持在 GitHub Actions 页面使用 `workflow_dispatch` 手动运行。

## 图片和数据存储方案

为避免 `main` 分支 Git 历史被每日图片无限撑大，工作流使用独立 `case-assets` 分支持久化：

- `data/cases.json`
- `data/latest.json`
- `data/source_health.json`
- `case_assets/cases/*.webp`

GitHub Pages 发布时只上传生成后的 `site/` 目录。前端公开数据位于 `site/data/*.json`，已经脱敏，不包含 `source_url`、来源网站、评分和抓取日期。

## 新增来源适配器的方法

1. 在 `src/collectors/` 新增适配器类，继承 `BaseCollector`。
2. 实现 `collect(category, days)`，返回 `Candidate` 列表。
3. 在 `src/collectors/registry.py` 注册 `adapter` 名称。
4. 在 `config/tasks.yml` 的 `sources` 增加来源配置。
5. 为该适配器补充 fixture 或 mock 测试，避免测试依赖真实网站。

每个来源必须独立失败，不能因为单个来源异常中断全流程。

## 下架机制

无需搭建后台。直接编辑：

- `config/blocked_cases.yml`
- `config/blocked_sources.yml`

可以按案例 id、来源链接、内容哈希、图片哈希、同分类鞋款标准名、来源 id 或域名屏蔽。

## 常见失败处理

- 全部分类新增为 0：工作流会跳过 Pages 覆盖，避免把旧站点刷空。
- 某个网站失败：只记录到 `data/source_health.json` 和 Actions Summary，其他来源继续补足。
- 图片下载失败：该候选不入库。
- WebP 转换失败：该候选不入库。
- AI 接口失败：自动使用本地规则模板，不阻断任务。
- 小红书失败：公开页经常变动，失败属于预期风险，系统会继续使用品牌官网和媒体来源补足。

## 小红书公开抓取说明

小红书适配器只访问公开页面，不登录、不保存 Cookie、不使用账号。由于公开页面可能要求验证、结构频繁变化或限制自动访问，抓取不稳定是正常情况。连续失败会记录在来源健康日志中，但不会终止日更。

## 图片版权说明

本项目用于设计研究和内部参考沉淀。公开展示图片前应确认使用场景符合平台规则和版权要求。若品牌、媒体或作者要求下架，可通过 `config/blocked_cases.yml` 或 `config/blocked_sources.yml` 立即屏蔽，并重新运行工作流。

## 测试

```bash
python -m unittest discover -s tests
```

测试覆盖配置校验、去重、评分、AI 降级、来源失败隔离、图片尺寸过滤、网页生成和前端脱敏。
