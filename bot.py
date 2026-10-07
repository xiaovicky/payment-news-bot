import feedparser
import requests
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

# ── 配置 ──────────────────────────────────────────────

# 北京时区
CST = timezone(timedelta(hours=8))

# 数据来源
SOURCES = {
    "Stripe Blog": "https://stripe.com/newsroom/news",
    "Visa Newsroom": "https://usa.visa.com/about-visa/newsroom.html",
    "Mastercard Newsroom": "https://newsroom.mastercard.com/",
    "PayPal Newsroom": "https://newsroom.paypal-corp.com/",
    "Adyen Press": "https://www.adyen.com/press-and-media",
    "Block News": "https://block.xyz/news",
    "Circle Pressroom": "https://www.circle.com/pressroom",
    "Coinbase Blog": "https://blog.coinbase.com/",
}

RSS_FEEDS = {
    "Payments Dive": "https://www.paymentsdive.com/feeds/news/",
    "Finextra": "https://www.finextra.com/rss/headlines.aspx",
    "PYMNTS": "https://www.pymnts.com/feed/",
    "The Paypers": "https://thepaypers.com/rss",
    "Stripe RSS": "https://stripe.com/blog/feed.rss",
    "Coinbase RSS": "https://blog.coinbase.com/feed",
    "Circle RSS": "https://www.circle.com/blog/rss.xml",
}

# X 账号（通过 RSSHub 桥）
X_ACCOUNTS = [
    "patrickc", "johncollison", "AlKellyVisa", "VisaCEO",
    "DanSchulman", "PayPalCEO", "jack", "jerallaire", "brian_armstrong",
    "gdb", "sriramk", "mattoshankar", "jasonkincaid", "david_sacks", "levie",
    "fredwilson", "bhorowitz", "jasonlk", "pmarca",
    "Stripe", "Visa", "Mastercard", "PayPal", "Adyen", "blocks", "circle", "coinbase",
]

RSS_BRIDGE_URL = "https://rsshub.app/twitter/user/{account}"

# 关键词过滤（与支付相关）
KEYWORDS = [
    "payment", "payments", "pay", "transaction", "merchant", "checkout",
    "fintech", "crypto", "stablecoin", "blockchain", "wallet",
    "cross-border", "remittance", "settlement", "clearing",
    "card", "credit", "debit", "pos", "acquiring",
    "api", "developer", "sdk", "integration",
    "revenue", "earnings", "quarter", "annual",
    "partnership", "acquisition", "merge", "launch", "announce",
    "regulation", "compliance", "license", "approval",
    "visa", "mastercard", "stripe", "paypal", "adyen", "block", "square",
    "circle", "coinbase", "usdc", "usdt", "bitcoin", "ethereum",
    "stablecoin", "cbdc", "digital currency", "open banking",
    "embedded finance", "bnpl", "installment", "payout",
]

# 状态文件
STATE_FILE = "sent_state.json"

# ── 工具函数 ──────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"sent_urls": [], "sent_titles": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()

def is_similar(title1, title2, threshold=0.75):
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() > threshold

def clean_html(raw_html):
    """去除 HTML 标签，只留纯文本"""
    if not raw_html:
        return ""
    text = re.sub(r'<[^>]+>', '', raw_html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_relevant(text):
    text_lower = text.lower()
    return any(kw in text_lower for kw in KEYWORDS)

def fetch_rss(url, source_name):
    """抓取 RSS feed"""
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title = clean_html(entry.get("title", ""))
            link = entry.get("link", "")
            summary = clean_html(entry.get("summary", entry.get("description", "")))
            published = entry.get("published_parsed", None)

            # 检查 24 小时内
            if published:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if (now - pub_dt).total_seconds() > 24 * 3600:
                    continue

            # 关键词过滤
            if not is_relevant(title + " " + summary):
                continue

            items.append({
                "title": title,
                "link": link,
                "summary": summary[:300],
                "source": source_name,
                "published": published,
            })
    except Exception as e:
        print(f"[WARN] {source_name} RSS failed: {e}")
    return items

def fetch_x_via_rss(account):
    """通过 RSSHub 桥抓 X 账号动态"""
    url = RSS_BRIDGE_URL.format(account=account)
    return fetch_rss(url, f"X@{account}")

def fetch_all():
    """抓取所有数据源"""
    all_items = []

    # RSS feeds
    for name, url in RSS_FEEDS.items():
        print(f"Fetching {name}...")
        all_items.extend(fetch_rss(url, name))

    # X accounts
    for account in X_ACCOUNTS:
        print(f"Fetching X @{account}...")
        all_items.extend(fetch_x_via_rss(account))

    return all_items

def deduplicate(items, state):
    """去重"""
    unique = []
    seen_urls = set(state["sent_urls"])
    seen_titles = state["sent_titles"]

    # DEBUG: 调试阶段暂时去掉去重，直接返回所有抓取到的条目
    return items

    for item in items:
        # URL 去重
        h = url_hash(item["link"])
        if h in seen_urls:
            continue

        # 标题相似度去重
        is_dup = False
        for existing in unique:
            if is_similar(item["title"], existing["title"]):
                is_dup = True
                break
        for sent_title in seen_titles[-200:]:
            if is_similar(item["title"], sent_title):
                is_dup = True
                break

        if not is_dup:
            unique.append(item)
            seen_urls.add(h)

    return unique

def translate_to_chinese(text):
    """用 Google Translate 免费接口翻译"""
    if not text:
        return ""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text[:500],  # 限制长度防止超时
        }
        resp = requests.get(url, params=params, timeout=10)
        result = resp.json()
        # 解析返回结果
        translated = "".join([item[0] for item in result[0] if item[0]])
        return translated
    except Exception as e:
        print(f"[WARN] Translate failed: {e}")
        return text  # 失败时返回原文

def generate_summary(items):
    """生成 AI 摘要（调用 OpenAI 或其他）"""
    for item in items:
        if not item["summary"]:
            item["summary"] = item["title"]
        item["one_liner"] = item["title"][:50]
        # 翻译标题和摘要
        item["title_cn"] = translate_to_chinese(item["title"])
        item["summary_cn"] = translate_to_chinese(item["summary"][:300])
    return items

def format_markdown(items, date_str):
    """生成 Markdown 消息，优化用户体验"""
    # 按来源分类
    news_items = []  # 资讯：媒体和官方博客
    post_items = []  # Post：X 高管发言

    for item in items:
        source = item.get("source", "")
        if source.startswith("X@"):
            post_items.append(item)
        else:
            news_items.append(item)

    lines = [f"# 📋 本日摘要【{date_str}】\n"]

    # 资讯部分
    if news_items:
        lines.append("## 📰 资讯")
        lines.append("")
        for idx, item in enumerate(news_items, 1):
            # 中文标题优先，英文缩进
            title_cn = item.get('title_cn', '')
            title_en = item['title']
            if title_cn and title_cn != title_en:
                lines.append(f"**{idx}. {title_cn}**")
                lines.append(f"  {title_en}")
            else:
                lines.append(f"**{idx}. {title_en}**")

            # 一句话总结
            lines.append(f"  └ 💡 {item['one_liner']}")

            # 摘要（如果有）
            if item['summary'] and len(item['summary']) > 50:
                summary_cn = item.get('summary_cn', '')
                if summary_cn and summary_cn != item['summary']:
                    lines.append(f"  └ 📝 {summary_cn[:150]}")
                else:
                    lines.append(f"  └ 📝 {item['summary'][:150]}")

            # 原文链接
            lines.append(f"  └ 🔗 [阅读原文]({item['link']})")
            lines.append("")

    # Post部分
    if post_items:
        lines.append("## 💬 高管动态")
        lines.append("")
        for item in post_items:
            # 提取账号名
            account = item['source'].replace('X@', '')
            # 内容优先，人名突出
            content = item['summary'][:250] if item['summary'] else item['title']
            content_cn = item.get('summary_cn', '')

            # 人名 + 引用块显示内容
            lines.append(f"**@{account}**")
            lines.append(f"> {content}")
            lines.append("")
            if content_cn and content_cn != content:
                lines.append(f"> 中文：{content_cn[:250]}")
                lines.append("")
            lines.append(f"[查看原文]({item['link']})")
            lines.append("")

    # 结尾统计
    total_news = len(news_items)
    total_posts = len(post_items)
    lines.append("---")
    lines.append(f"📊 今日共 {total_news} 条资讯，{total_posts} 条高管动态")

    return "\n".join(lines)

def send_dingtalk(webhook, message):
    """发送钉钉消息"""
    headers = {"Content-Type": "application/json"}
    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": message.split("\n")[0],
            "text": message,
        }
    }
    resp = requests.post(webhook, json=data, headers=headers, timeout=10)
    result = resp.json()
    if result.get("errcode") != 0:
        raise Exception(f"DingTalk send failed: {result}")
    return result

# ── 主函数 ────────────────────────────────────────────

def main():
    print("=" * 50)
    print(f"Starting daily payment news bot at {datetime.now(CST).isoformat()}")

    # 加载状态
    state = load_state()
    print(f"Loaded state: {len(state['sent_urls'])} sent URLs")

    # 抓取
    all_items = fetch_all()
    print(f"Fetched {len(all_items)} raw items")

    # 去重
    unique_items = deduplicate(all_items, state)
    print(f"After dedup: {len(unique_items)} items")

    if not unique_items:
        print("No new items today. Skipping.")
        return

    # 生成摘要
    items = generate_summary(unique_items)

    # 生成 Markdown
    today = datetime.now(CST)
    date_str = today.strftime("%Y年%m月%d日")
    markdown = format_markdown(items, date_str)

    # 发送钉钉
    webhook = os.environ.get("DINGTALK_WEBHOOK")
    if not webhook:
        raise Exception("DINGTALK_WEBHOOK not set in environment")

    print(f"Sending to DingTalk...")
    send_dingtalk(webhook, markdown)
    print("Sent successfully!")

    # 更新状态
    state["sent_urls"].extend([url_hash(i["link"]) for i in items])
    state["sent_titles"].extend([i["title"] for i in items])
    # 保留最近 500 条记录，防止文件过大
    state["sent_urls"] = state["sent_urls"][-500:]
    state["sent_titles"] = state["sent_titles"][-500:]
    save_state(state)
    print(f"State saved. Total sent: {len(state['sent_urls'])}")

    print("=" * 50)

if __name__ == "__main__":
    main()
