"""
WaveDesk - 해운 아침 브리핑
크롤링 + HTML 생성 + GitHub 업로드
실행: python crawl_and_publish.py [--output DIR] [--no-push]
"""

import subprocess, sys, json, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 의존성 ──────────────────────────────────────────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "beautifulsoup4", "lxml", "-q",
                           "--break-system-packages"])
    import requests
    from bs4 import BeautifulSoup

KST     = timezone(timedelta(hours=9))
NOW     = datetime.now(KST)
WEEKDAY = ["월","화","수","목","금","토","일"][NOW.weekday()]
DATE_STR = NOW.strftime(f"%Y년 %m월 %d일 ({WEEKDAY})")
TIME_STR = NOW.strftime("%H:%M")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA}
TIMEOUT = 12

# ══════════════════════════════════════════════════════════════════════════
# 1. 시황 지수
# ══════════════════════════════════════════════════════════════════════════

def get_indices():
    base = {
        "BDI":  {"value": "—", "change": "", "label": "발틱운임지수"},
        "SCFI": {"value": "—", "change": "", "label": "상하이컨운임지수"},
        "CCFI": {"value": "—", "change": "", "label": "중국컨운임지수"},
        "KCCI": {"value": "—", "change": "", "label": "한국컨운임지수"},
    }
    # 국가물류통합정보센터
    try:
        r = requests.get("https://www.klnet.co.kr/information/shipinfo_sub01.asp",
                         headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "lxml")
        for row in soup.select("table tr"):
            cols = [c.get_text(strip=True) for c in row.select("td")]
            if len(cols) >= 2:
                for key in ("BDI","SCFI","CCFI","KCCI"):
                    if key in cols[0]:
                        base[key]["value"]  = cols[1]
                        base[key]["change"] = cols[2] if len(cols) > 2 else ""
    except Exception:
        pass
    # 한국해양진흥공사 KCCI
    if base["KCCI"]["value"] == "—":
        try:
            r = requests.get("https://www.kobc.or.kr/kor/contents/kcci/kcci.do",
                             headers=HEADERS, timeout=TIMEOUT)
            soup = BeautifulSoup(r.text, "lxml")
            cells = soup.select(".kcci-index td, table.kcci td")
            if cells:
                base["KCCI"]["value"]  = cells[0].get_text(strip=True)
                base["KCCI"]["change"] = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        except Exception:
            pass
    return base


# ══════════════════════════════════════════════════════════════════════════
# 2. 뉴스 수집
# ══════════════════════════════════════════════════════════════════════════

def parse_rss(url, source, label_ko, max_items=6):
    """RSS XML 파싱 → [{title, url, source, label}]"""
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "utf-8"
        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # RSS 2.0
        for item in root.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            if title and link:
                items.append({"title": title, "url": link,
                               "source": source, "label": label_ko})
        # Atom
        if not items:
            for entry in root.findall(".//atom:entry", ns)[:max_items]:
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href","") if link_el is not None else ""
                if title and link:
                    items.append({"title": title, "url": link,
                                   "source": source, "label": label_ko})
    except Exception:
        pass
    return items


def fetch_ksg():
    """코리아쉬핑가제트 HTML 파싱"""
    items = []
    try:
        r = requests.get("https://www.ksg.co.kr/news/main_news.jsp",
                         headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            t = a.get_text(strip=True)
            h = a["href"]
            if (len(t) > 12 and
                    ("pNum=" in h or "newsView" in h) and
                    any(k in t for k in ("선","항","해운","운임","물류","조선","컨","벌크","탱커"))):
                if not h.startswith("http"):
                    h = "https://www.ksg.co.kr" + h
                items.append({"title": t, "url": h,
                               "source": "KSG", "label": "코리아쉬핑가제트"})
                if len(items) >= 6:
                    break
    except Exception:
        pass
    return items


def fetch_smnews():
    """쉬핑뉴스넷 HTML 파싱"""
    items = []
    try:
        r = requests.get("https://www.shippingnewsnet.com/",
                         headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.select("h2 a, h3 a, .entry-title a")[:6]:
            t = a.get_text(strip=True)
            h = a.get("href", "")
            if t and len(t) > 8 and h.startswith("http"):
                items.append({"title": t, "url": h,
                               "source": "쉬핑뉴스넷", "label": "쉬핑뉴스넷"})
    except Exception:
        pass
    return items


def get_news():
    news = []
    # 해외 — RSS
    news += parse_rss(
        "https://services.tradewindsnews.com/api/feed/rss",
        "TradeWinds", "TradeWinds", 5)
    news += parse_rss(
        "https://splash247.com/feed/",
        "Splash247", "Splash247", 5)
    news += parse_rss(
        "https://www.hellenicshippingnews.com/feed/",
        "Hellenic", "Hellenic Shipping News", 5)
    # 국내
    news += fetch_ksg()
    news += fetch_smnews()
    # 중복 제거
    seen, result = set(), []
    for n in news:
        key = n["title"][:30]
        if key not in seen:
            seen.add(key)
            result.append(n)
    return result[:20]


# ══════════════════════════════════════════════════════════════════════════
# 3. HTML 생성
# ══════════════════════════════════════════════════════════════════════════

SOURCE_STYLE = {
    "TradeWinds":  {"bg": "#e8f0fe", "fg": "#1a56db", "flag": "🌐"},
    "Splash247":   {"bg": "#fce8e6", "fg": "#c0392b", "flag": "🌐"},
    "Hellenic":    {"bg": "#e6f4ea", "fg": "#137333", "flag": "🌐"},
    "KSG":         {"bg": "#fff3e0", "fg": "#e65100", "flag": "🇰🇷"},
    "쉬핑뉴스넷":   {"bg": "#f3e5f5", "fg": "#6a1b9a", "flag": "🇰🇷"},
}

SOURCE_URL = {
    "TradeWinds": "https://www.tradewindsnews.com/latest",
    "Splash247":  "https://splash247.com/",
    "Hellenic":   "https://www.hellenicshippingnews.com/",
    "KSG":        "https://www.ksg.co.kr/news/main_news.jsp",
    "쉬핑뉴스넷":  "https://www.shippingnewsnet.com/",
}

def dir_cls(change_str):
    s = re.sub(r"[^0-9.\-]", "", str(change_str))
    try:
        v = float(s)
        if v > 0: return "up", "▲"
        if v < 0: return "dn", "▼"
    except Exception:
        pass
    return "neu", "—"


def build_html(indices, news):
    # 시황 카드
    idx_html = ""
    for key, d in indices.items():
        cls, arrow = dir_cls(d.get("change",""))
        chg = d.get("change","").strip()
        chg_str = f"{arrow} {chg}" if chg and chg not in ("0","—","") else "전일 동일"
        idx_html += f"""
      <div class="idx-card">
        <div class="idx-label">{d['label']}</div>
        <div class="idx-key">{key}</div>
        <div class="idx-val">{d['value']}</div>
        <div class="idx-chg {cls}">{chg_str}</div>
      </div>"""

    # 뉴스 목록 — 소스별 그룹
    # 소스 순서: 해외 → 국내
    source_order = ["TradeWinds","Splash247","Hellenic","KSG","쉬핑뉴스넷"]
    grouped = {s: [] for s in source_order}
    for n in news:
        s = n["source"]
        if s in grouped:
            grouped[s].append(n)

    news_sections = ""
    for src in source_order:
        items = grouped[src]
        if not items:
            continue
        st = SOURCE_STYLE.get(src, {"bg":"#f0f0f0","fg":"#333","flag":"📰"})
        src_url = SOURCE_URL.get(src, "#")
        label = items[0]["label"]
        rows = ""
        for n in items:
            title = n["title"][:70] + ("…" if len(n["title"]) > 70 else "")
            rows += f"""
          <a class="news-row" href="{n['url']}" target="_blank" rel="noopener noreferrer">
            <span class="news-title">{title}</span>
            <span class="news-link-icon">↗</span>
          </a>"""
        news_sections += f"""
      <div class="news-source-block">
        <div class="source-header">
          <span class="source-flag">{st['flag']}</span>
          <a class="source-name" href="{src_url}" target="_blank"
             style="color:{st['fg']};background:{st['bg']}">{label}</a>
        </div>
        <div class="news-rows">{rows}
        </div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WaveDesk · 해운 아침 브리핑</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans KR',sans-serif;
      background:#f0f4f8;color:#1a1a2e;min-height:100vh}}
.container{{max-width:960px;margin:0 auto;padding:2rem 1.25rem}}

/* 헤더 */
.header{{display:flex;justify-content:space-between;align-items:flex-end;
         margin-bottom:1.75rem;padding-bottom:1rem;
         border-bottom:2px solid #2563eb}}
.brand{{display:flex;align-items:baseline;gap:10px}}
.brand-name{{font-size:1.5rem;font-weight:700;color:#1e3a8a;letter-spacing:-0.5px}}
.brand-sub{{font-size:0.8rem;color:#6b7280;font-weight:400}}
.header-meta{{text-align:right;font-size:0.78rem;color:#9ca3af;line-height:1.6}}

/* 시황 지수 */
.section-label{{font-size:0.78rem;font-weight:600;text-transform:uppercase;
                letter-spacing:.8px;color:#6b7280;margin-bottom:.6rem}}
.idx-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:2rem}}
.idx-card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
           padding:.9rem 1.1rem;position:relative}}
.idx-label{{font-size:.72rem;color:#9ca3af;margin-bottom:1px}}
.idx-key{{font-size:.7rem;font-weight:700;color:#6b7280;margin-bottom:.3rem}}
.idx-val{{font-size:1.45rem;font-weight:700;color:#111827}}
.idx-chg{{font-size:.78rem;margin-top:.25rem}}
.up{{color:#dc2626}}.dn{{color:#2563eb}}.neu{{color:#9ca3af}}

/* 뉴스 */
.news-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:2rem}}
.news-source-block{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}}
.source-header{{display:flex;align-items:center;gap:8px;
                padding:.65rem 1rem;border-bottom:1px solid #f3f4f6}}
.source-flag{{font-size:.9rem}}
.source-name{{font-size:.75rem;font-weight:600;padding:2px 8px;
              border-radius:4px;text-decoration:none;letter-spacing:.2px}}
.source-name:hover{{opacity:.8}}
.news-rows{{display:flex;flex-direction:column}}
.news-row{{display:flex;align-items:center;justify-content:space-between;
           padding:.55rem 1rem;border-bottom:1px solid #f9fafb;
           text-decoration:none;color:inherit;gap:8px;
           transition:background .12s}}
.news-row:last-child{{border-bottom:none}}
.news-row:hover{{background:#f8faff}}
.news-title{{font-size:.82rem;line-height:1.45;color:#111827;flex:1}}
.news-link-icon{{font-size:.8rem;color:#9ca3af;flex-shrink:0}}

/* 바로가기 */
.links-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:1.5rem}}
.link-card{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;
            padding:.75rem 1rem;text-decoration:none;color:inherit;
            transition:border-color .15s}}
.link-card:hover{{border-color:#2563eb}}
.link-card .lc-name{{font-size:.82rem;font-weight:600;color:#111827}}
.link-card .lc-sub{{font-size:.72rem;color:#9ca3af;margin-top:2px}}

/* 푸터 */
.footer{{font-size:.72rem;color:#d1d5db;text-align:center;
         padding-top:.75rem;border-top:1px solid #e5e7eb}}

@media(max-width:640px){{
  .idx-grid{{grid-template-columns:repeat(2,1fr)}}
  .news-grid{{grid-template-columns:1fr}}
  .links-grid{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <div class="brand">
      <span class="brand-name">⚓ WaveDesk</span>
      <span class="brand-sub">해운 아침 브리핑</span>
    </div>
    <div class="header-meta">
      {DATE_STR}<br>
      업데이트 {TIME_STR} KST
    </div>
  </div>

  <div class="section-label">📊 해운 시황 지수</div>
  <div class="idx-grid">{idx_html}
  </div>

  <div class="section-label">📰 최신 해운 뉴스</div>
  <div class="news-grid">{news_sections}
  </div>

  <div class="section-label">🔗 주요 사이트</div>
  <div class="links-grid">
    <a class="link-card" href="https://www.tradewindsnews.com/latest" target="_blank">
      <div class="lc-name">TradeWinds</div>
      <div class="lc-sub">글로벌 해운 전문 미디어 (영문)</div>
    </a>
    <a class="link-card" href="https://splash247.com/" target="_blank">
      <div class="lc-name">Splash247</div>
      <div class="lc-sub">해운·오프쇼어 뉴스 (영문)</div>
    </a>
    <a class="link-card" href="https://www.hellenicshippingnews.com/" target="_blank">
      <div class="lc-name">Hellenic Shipping News</div>
      <div class="lc-sub">국제 해운 뉴스 (영문)</div>
    </a>
    <a class="link-card" href="https://www.ksg.co.kr/news/main_news.jsp" target="_blank">
      <div class="lc-name">코리아쉬핑가제트</div>
      <div class="lc-sub">국내 해운 전문 미디어</div>
    </a>
    <a class="link-card" href="https://www.shippingnewsnet.com/" target="_blank">
      <div class="lc-name">쉬핑뉴스넷</div>
      <div class="lc-sub">국내 해운물류 뉴스</div>
    </a>
    <a class="link-card" href="https://www.balticexchange.com/en/data/indices.html" target="_blank">
      <div class="lc-name">Baltic Exchange</div>
      <div class="lc-sub">BDI 공식 사이트</div>
    </a>
    <a class="link-card" href="https://www.kobc.or.kr/kor/contents/kcci/kcci.do" target="_blank">
      <div class="lc-name">한국해양진흥공사 KCCI</div>
      <div class="lc-sub">한국 컨테이너 운임지수</div>
    </a>
    <a class="link-card" href="https://www.klnet.co.kr/information/shipinfo_sub01.asp" target="_blank">
      <div class="lc-name">국가물류통합정보센터</div>
      <div class="lc-sub">BDI · SCFI · CCFI</div>
    </a>
    <a class="link-card" href="https://www.alphaliner.com/top100" target="_blank">
      <div class="lc-name">Alphaliner Top 100</div>
      <div class="lc-sub">컨테이너 선사 순위</div>
    </a>
  </div>

  <div class="footer">
    WaveDesk · 매일 08:00 KST 자동 업데이트 · GitHub Pages 호스팅<br>
    시황 지수 미표시 시 하단 링크로 직접 확인하세요.
  </div>

</div>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════
# 4. 실행
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=".")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    print(f"[WaveDesk] {DATE_STR} {TIME_STR} 크롤링 시작")
    indices = get_indices()
    news    = get_news()
    print(f"  지수: {sum(1 for v in indices.values() if v['value']!='—')}개 수집")
    print(f"  뉴스: {len(news)}건 수집")

    html = build_html(indices, news)
    out  = Path(args.output) / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"  HTML 저장: {out.resolve()}")

    if not args.no_push:
        try:
            subprocess.run(["git","add","index.html"], cwd=args.output, check=True)
            subprocess.run(["git","commit","-m",
                            f"briefing: {NOW.strftime('%Y-%m-%d %H:%M')} KST"],
                           cwd=args.output, check=True)
            subprocess.run(["git","push"], cwd=args.output, check=True)
            print("  GitHub 업로드 완료")
        except subprocess.CalledProcessError as e:
            print(f"  git 오류: {e}")
    else:
        print("  --no-push: git push 생략")
