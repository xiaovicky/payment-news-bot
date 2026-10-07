import feedparser
import requests
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

# ── 配置 ──────────────────────────────────────────────

CST = timezone(timedelta(hours=8))

# 核心关键词（与 Alipay+ 战略相关）
CORE_KEYWORDS = [
    # 竞品和合作伙伴
    "alipay", "ant group", "ant international", "alipay+",
    "grabpay", "touch n go", "tng", "gcash", "paytm", "phonepe",
    "kakao pay", "line pay", "paypay", "boost", "dana",
    # 地区
    "singapore", "indonesia", "malaysia", "philippines", "vietnam",
    "thailand", "india", "korea", "japan", "uae", "saudi",
    "southeast asia", "asia pacific", "apac",
    # 支付基础设施
    "qr payment", "qr code", "cross-border", "remittance",
    "instant payment", "real-time payment", "fast payment",
    "iso 20022", "a2a", "account-to-account",
    "payment interoperability", "payment link",
    # 监管和政策
    "mas", "monetary authority of singapore", "bank indonesia", "bi",
    "rbi", "reserve bank of india", "bsp", "bangko sentral",
    "bank negara malaysia", "bnm", "cbdc", "central bank digital",
    "stablecoin", "regulation", "licensing", "payment license",
    # 技术趋势
    "tokenization", "digital wallet", "e-wallet", "super app",
    "embedded finance", "open banking", "api", "sdk",
    "fraud detection", "risk management", "compliance",
    "ai in payments", "machine learning",
]

# 低优先级过滤词（减少噪音）
NOISE_KEYWORDS = [
    "car dealership", "carmax", "coffee shop", "restaurant",
    "retail store", "small business loan", "mortgage",
    "credit card rewards", "cash back", "travel insurance",
]

# 高优先级关键词（需要标记为 🔴）
HIGH_PRIORITY_KEYWORDS = [
    "alipay", "ant group", "ant international", "alipay+",
    "grabpay", "gcash", "paytm", "phonepe",
    "singapore", "indonesia", "malaysia", "india",
    "mas", "rbi", "bi ", "bsp", "bnm",
    "stablecoin", "cbdc", "iso 20022",
]

# 新闻源（聚焦亚太和全球支付格局）
RSS_FEEDS = {
    # 全球权威
    "Payments Dive": "https://www.paymentsdive.com/feeds/news/",
    "Finextra": "https://www.finextra.com/rss/headlines.aspx",
    "The Paypers": "https://thepaypers.com/rss",
    # 亚太聚焦
    "Asian Banker": "https://www.theasianbanker.com/rss.xml",
    "FinTech Futures": "https://www.fintechfutures.com/feed/",
    # 官方博客
    "Stripe Blog": "https://stripe.com/blog/feed.rss",
    "Circle Blog": "https://www.circle.com/blog/rss.xml",
    "Coinbase Blog": "https://blog.coinbase.com/feed",
}

# X 账号（聚焦全球支付高管和亚太监管）
X_ACCOUNTS = [
    # 全球支付领袖
    "patrickc", "johncollison",  # Stripe
    "jerallaire",  # Circle
    "brian_armstrong",  # Coinbase
    "jack",  # Block
    # 亚太监管（关键）
    "MAS_sg",  # 新加坡金管局
    "bankindonesia",  # 印尼央行
    "RBI",  # 印度央行
    "bnm_official",  # 马来西亚央行
    "bsp_official",  # 菲律宾央行
    # 行业观察者
    "SGFinTechFest",  # 新加坡金融科技节
    "FinTechAssocSG",  # 新加坡金融科技协会
]

RSS_BRIDGE_URL = "https://rsshub.app/twitter/user/{account}"

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

def is_relevant(text):
    """检查是否与 Alipay+ 战略相关"""
    text_lower = text.lower()
    # 排除噪音
    if any(noise in text_lower for noise in NOISE_KEYWORDS):
        return False
    # 检查核心关键词
    return any(kw in text_lower for kw in CORE_KEYWORDS)

def get_priority(text):
    """判断优先级"""
    text_lower = text.lower()
    if any(kw in text_lower for kw in HIGH_PRIORITY_KEYWORDS):
        return "high"
    return "normal"

def clean_html(raw_html):
    """去除 HTML 标签"""
    if not raw_html:
        return ""
    text = re.sub(r'<[^>]+>', '', raw_html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def translate_to_chinese(text):
    """用 MyMemory API 翻译"""
    if not text:
        return ""
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {
            "q": text[:500],
            "langpair": "en|zh-CN",
        }
        resp = requests.get(url, params=params, timeout=10)
        result = resp.json()
        translated = result.get("responseData", {}).get("translatedText", "")
        if translated and translated != text:
            return translated
        return text
    except Exception as e:
        print(f"[ERROR] Translate failed: {e}")
        return text

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

            # 24 小时内
            if published:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if (now - pub_dt).total_seconds() > 24 * 3600:
                    continue

            # 关键词过滤
            if not is_relevant(title + " " + summary):
                continue

            priority = get_priority(title + " " + summary)

            items.append({
                "title": title,
                "link": link,
                "summary": summary[:300],
                "source": source_name,
                "published": published,
                "priority": priority,
            })
    except Exception as e:
        print(f"[WARN] {source_name} RSS failed: {e}")
    return items

def fetch_x_via_rss(account):
    """通过 RSSHub 桥抓 X 账号"""
    url = RSS_BRIDGE_URL.format(account=account)
    return fetch_rss(url, f"X@{account}")

def fetch_all():
    """抓取所有数据源"""
    all_items = []

    for name, url in RSS_FEEDS.items():
        print(f"Fetching {name}...")
        all_items.extend(fetch_rss(url, name))

    for account in X_ACCOUNTS:
        print(f"Fetching X @{account}...")
        all_items.extend(fetch_x_via_rss(account))

    return all_items

def deduplicate(items, state):
    """去重"""
    # DEBUG: 暂时禁用
    return items

    unique = []
    seen_urls = set(state["sent_urls"])
    seen_titles = state["sent_titles"]

    for item in items:
        h = url_hash(item["link"])
        if h in seen_urls:
            continue

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

def generate_summary(items):
    """生成摘要和翻译"""
    for item in items:
        if not item["summary"]:
            item["summary"] = item["title"]
        item["one_liner"] = item["title"][:60]
        item["title_cn"] = translate_to_chinese(item["title"])
        item["summary_cn"] = translate_to_chinese(item["summary"][:300])
    return items

def format_markdown(items, date_str):
    """生成 Markdown 消息，按优先级排序"""
    # 按优先级分类
    high_priority = [i for i in items if i.get("priority") == "high"]
    normal_priority = [i for i in items if i.get("priority") != "high"]

    # 再按类型分类
    high_news = [i for i in high_priority if not i["source"].startswith("X@")]
    high_posts = [i for i in high_priority if i["source"].startswith("X@")]
    normal_news = [i for i in normal_priority if not i["source"].startswith("X@")]
    normal_posts = [i for i in normal_priority if i["source"].startswith("X@")]

    lines = [f"# 📋 Alipay+ 情报摘要【{date_str}】\n"]

    # 🔴 高优先级
    if high_priority:
        lines.append("## 🔴 高优先级\n")

        if high_news:
            lines.append("### 关键动态\n")
            for idx, item in enumerate(high_news, 1):
                title_cn = item.get('title_cn', '')
                title_en = item['title']
                if title_cn and title_cn != title_en:
                    lines.append(f"**{idx}. {title_cn}**")
                    lines.append(f"  {title_en}")
                else:
                    lines.append(f"**{idx}. {title_en}**")

                lines.append(f"  └ 💡 {item['one_liner']}")
                if item['summary'] and len(item['summary']) > 50:
                    summary_cn = item.get('summary_cn', '')
                    if summary_cn and summary_cn != item['summary']:
                        lines.append(f"  └ 📝 {summary_cn[:200]}")
                    else:
                        lines.append(f"  └ 📝 {item['summary'][:200]}")
                lines.append(f"  └ 🔗 [阅读原文]({item['link']})")
                lines.append("")

        if high_posts:
            lines.append("### 关键声音\n")
            for item in high_posts:
                account = item['source'].replace('X@', '')
                content = item['summary'][:250] if item['summary'] else item['title']
                content_cn = item.get('summary_cn', '')

                lines.append(f"**@{account}**")
                lines.append(f"> {content}")
                lines.append("")
                if content_cn and content_cn != content:
                    lines.append(f"> 中文：{content_cn[:250]}")
                    lines.append("")
                lines.append(f"[查看原文]({item['link']})")
                lines.append("")

    # 🟡 行业动态
    if normal_news:
        lines.append("## 🟡 行业动态\n")
        for idx, item in enumerate(normal_news, 1):
            title_cn = item.get('title_cn', '')
            title_en = item['title']
            if title_cn and title_cn != title_en:
                lines.append(f"**{idx}. {title_cn}**")
            else:
                lines.append(f"**{idx}. {title_en}**")
            lines.append(f"  └ 🔗 [阅读原文]({item['link']})")
            lines.append("")

    if normal_posts:
        lines.append("### 行业声音\n")
        for item in normal_posts:
            account = item['source'].replace('X@', '')
            content = item['summary'][:200] if item['summary'] else item['title']
            lines.append(f"**@{account}**")
            lines.append(f"> {content}")
            lines.append(f"[查看原文]({item['link']})")
            lines.append("")

    # 统计
    total = len(items)
    high_count = len(high_priority)
    lines.append("---")
    lines.append(f"📊 今日共 {total} 条情报（{high_count} 条高优先级）")

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
    print(f"Starting Alipay+ CTO intelligence bot at {datetime.now(CST).isoformat()}")

    state = load_state()
    print(f"Loaded state: {len(state['sent_urls'])} sent URLs")

    all_items = fetch_all()
    print(f"Fetched {len(all_items)} raw items")

    unique_items = deduplicate(all_items, state)
    print(f"After dedup: {len(unique_items)} items")

    if not unique_items:
        print("No new items today. Skipping.")
        return

    items = generate_summary(unique_items)

    today = datetime.now(CST)
    date_str = today.strftime("%Y年%m月%d日")
    markdown = format_markdown(items, date_str)

    webhook = os.environ.get("DINGTALK_WEBHOOK")
    if not webhook:
        raise Exception("DINGTALK_WEBHOOK not set in environment")

    print(f"Sending to DingTalk...")
    send_dingtalk(webhook, markdown)
    print("Sent successfully!")

    state["sent_urls"].extend([url_hash(i["link"]) for i in items])
    state["sent_titles"].extend([i["title"] for i in items])
    state["sent_urls"] = state["sent_urls"][-500:]
    state["sent_titles"] = state["sent_titles"][-500:]
    save_state(state)
    print(f"State saved. Total sent: {len(state['sent_urls'])}")

    print("=" * 50)

if __name__ == "__main__":
    main()
