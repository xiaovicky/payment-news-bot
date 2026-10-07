# 每日全球支付科技动态推送

每天早上自动抓取 Stripe / Visa / Mastercard / PayPal / Adyen / Block / Circle / Coinbase 等公司动态，推送到钉钉群。

## 数据来源

- 8 家公司官方博客（RSS）
- 4 家行业媒体（Payments Dive / Finextra / PYMNTS / The Paypers）
- 19 个 X 高管账号（通过 RSSHub 桥）

## 部署步骤

1. **Fork 本仓库** 到你的 GitHub 账号

2. **添加钉钉 Webhook 到 Secrets**
   - 仓库页面 → `Settings` → `Secrets and variables` → `Actions`
   - 点击 `New repository secret`
   - Name: `DINGTALK_WEBHOOK`
   - Secret: 你的钉钉机器人 webhook 地址
   - 点击 `Add secret`

3. **确认定时任务**
   - 仓库页面 → `Actions` → 确认 workflow 已启用
   - 每天早上 7 点自动运行

## 手动触发

仓库页面 → `Actions` → `Daily Payment News Bot` → `Run workflow`

## 文件说明

| 文件 | 作用 |
|------|------|
| `bot.py` | 主脚本：抓取 → 去重 → 生成摘要 → 发送钉钉 |
| `requirements.txt` | Python 依赖 |
| `.github/workflows/daily-bot.yml` | GitHub Actions 定时任务配置 |
| `sent_state.json` | 发送记录（防重复），自动生成 |

## 自定义

- 修改 `bot.py` 中 `X_ACCOUNTS` 添加/删除 X 账号
- 修改 `bot.py` 中 `RSS_FEEDS` 添加/删除 RSS 源
- 修改 `bot.py` 中 `KEYWORDS` 调整关键词过滤规则
- 修改 `.github/workflows/daily-bot.yml` 中 `cron` 调整定时时间
