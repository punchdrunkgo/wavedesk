"""
WaveDesk - 해운 아침 브리핑
BDI(쉬핑뉴스넷) + KCCI(한국해양진흥공사) + 해외뉴스 번역 + 국내뉴스
"""

import subprocess, sys, re, xml.etree.ElementTree as ET, json, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "beautifulsoup4", "lxml", "-q",
                           "--break-system-packages"])
    import requests
    from bs4 import BeautifulSoup

KST      = timezone(timedelta(hours=9))
NOW      = datetime.now(KST)
WEEKDAY  = ["월","화","수","목","금","토","일"][NOW.weekday()]
DATE_STR = NOW.strftime(f"%Y년 %m월 %d일 ({WEEKDAY})")
TIME_STR = NOW.strftime("%H:%M")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/",
}
TIMEOUT = 15

# ══════════════════════════════════════════════════════════════════════════
# 1. 시황 지수
# ══════════════════════════════════════════════════════════════════════════

def get_indices():
    base = {
        "BDI":  {"value": "—", "change": "", "label": "발틱운임지수",
                 "date": "", "url": "https://www.shippingnewsnet.com/sdata/page.html?term=1",
                 "note": "매일 (발틱해운거래소, 쉬핑뉴스넷 제공)"},
        "KCCI": {"value": "—", "change": "", "label": "한국컨운임지수",
                 "date": "", "url": "https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000",
                 "note": "매주 월요일 14:00 (한국해양진흥공사)"},
    }

    # ── BDI: 쉬핑뉴스넷 ──────────────────────────────────────────────
    try:
        r = requests.get(
            "https://www.shippingnewsnet.com/sdata/page.html?term=1",
            headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "lxml")
        data_rows = []
        for row in soup.select("table tr"):
            cols = [td.get_text(strip=True) for td in row.select("td")]
            if len(cols) >= 2 and re.match(r"\d{4}-\d{2}-\d{2}", cols[0]):
                data_rows.append(cols)
        if data_rows:
            latest, prev = data_rows[0], data_rows[1] if len(data_rows) > 1 else None
            chg = ""
            if prev:
                try:
                    diff = int(latest[1].replace(",","")) - int(prev[1].replace(",",""))
                    chg = f"+{diff}" if diff >= 0 else str(diff)
                except Exception:
                    pass
            base["BDI"].update({"value": latest[1], "change": chg, "date": latest[0]})
    except Exception as e:
        print(f"  [BDI 오류] {e}")

    # ── KCCI: 한국해양진흥공사 메인 ──────────────────────────────────
    try:
        r = requests.get(
            "https://www.kobc.or.kr/ebz/shippinginfo/main.do",
            headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            t = a.get_text(" ", strip=True)
            if "Container Composite Index" in t:
                nums = re.findall(r"[\d,]+(?:\.\d+)?", t)
                m_chg = re.search(r"([+\-][\d.]+%)", t)
                if nums:
                    base["KCCI"].update({
                        "value": nums[0],
                        "change": m_chg.group(1) if m_chg else "",
                        "date": NOW.strftime("%Y-%m-%d")
                    })
                break
    except Exception as e:
        print(f"  [KCCI 오류] {e}")

    return base


# ══════════════════════════════════════════════════════════════════════════
# 2. 뉴스 수집
# ══════════════════════════════════════════════════════════════════════════

def parse_rss(url, source, label, max_items=5):
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or item.findtext("guid") or "").strip()
            if title and link and link.startswith("http"):
                items.append({"title": title, "title_ko": "",
                               "url": link, "source": source, "label": label})
    except Exception:
        pass
    return items


def fetch_google_news_ko():
    """Google 뉴스 RSS - 한국어 해운 키워드 검색 (GitHub Actions 서버에서도 작동)"""
    items = []
    # 키워드별 RSS URL (Google 뉴스는 해외 서버에서도 차단 없음)
    queries = ["해운+운임", "해운+물류", "컨테이너+운임"]
    for q in queries:
        url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:5]:
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link") or "").strip()
                # Google 뉴스 링크는 리디렉션 URL — source 태그에서 언론사 추출
                source_el = item.find("source")
                src_name = source_el.text.strip() if source_el is not None else "국내뉴스"
                if title and link:
                    items.append({
                        "title": title, "title_ko": title,
                        "url": link,
                        "source": "구글뉴스", "label": src_name
                    })
        except Exception:
            pass
        if len(items) >= 10:
            break
    return items


def translate_titles(news_list):
    """해외 뉴스 제목을 Claude API로 일괄 번역"""
    foreign = [n for n in news_list if n["source"] in ("TradeWinds","Splash247","Hellenic") and not n["title_ko"]]
    if not foreign:
        return news_list

    titles = [n["title"] for n in foreign]
    prompt = (
        "아래 영문 해운 뉴스 제목들을 자연스러운 한국어로 번역해줘. "
        "JSON 배열로만 응답해. 다른 말은 하지 마.\n\n"
        + json.dumps(titles, ensure_ascii=False)
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        data = resp.json()
        text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
        text = re.sub(r"```json|```", "", text).strip()
        translated = json.loads(text)
        fi = 0
        for n in news_list:
            if n["source"] in ("TradeWinds","Splash247","Hellenic") and not n["title_ko"]:
                if fi < len(translated):
                    n["title_ko"] = translated[fi]
                    fi += 1
    except Exception as e:
        print(f"  [번역 오류] {e}")
        for n in foreign:
            n["title_ko"] = n["title"]
    return news_list


def get_news():
    news = []
    news += parse_rss("https://services.tradewindsnews.com/api/feed/rss", "TradeWinds", "TradeWinds", 5)
    news += parse_rss("https://splash247.com/feed/", "Splash247", "Splash247", 5)
    news += parse_rss("https://www.hellenicshippingnews.com/feed/", "Hellenic", "Hellenic Shipping News", 4)
    news += fetch_google_news_ko()

    seen, result = set(), []
    for n in news:
        key = n["title"][:25]
        if key not in seen:
            seen.add(key)
            result.append(n)

    result = result[:22]
    result = translate_titles(result)
    return result


# ══════════════════════════════════════════════════════════════════════════
# 3. HTML 생성
# ══════════════════════════════════════════════════════════════════════════

SOURCE_STYLE = {
    "TradeWinds": {"bg": "#e8f0fe", "fg": "#1a56db", "flag": "🌐"},
    "Splash247":  {"bg": "#fce8e6", "fg": "#c0392b", "flag": "🌐"},
    "Hellenic":   {"bg": "#e6f4ea", "fg": "#137333", "flag": "🌐"},
    "구글뉴스":    {"bg": "#fff3e0", "fg": "#e65100", "flag": "🇰🇷"},
}
SOURCE_URL = {
    "TradeWinds": "https://www.tradewindsnews.com/latest",
    "Splash247":  "https://splash247.com/",
    "Hellenic":   "https://www.hellenicshippingnews.com/",
    "구글뉴스":    "https://news.google.com/search?q=해운+운임&hl=ko&gl=KR&ceid=KR:ko",
}

def dir_cls(chg):
    s = re.sub(r"[^0-9.\-]", "", str(chg))
    try:
        v = float(s)
        if v > 0: return "up", "▲"
        if v < 0: return "dn", "▼"
    except Exception:
        pass
    return "neu", "—"


def build_html(indices, news):
    # 지수 카드 (BDI + KCCI 2개)
    idx_html = ""
    for key, d in indices.items():
        cls, arrow = dir_cls(d.get("change",""))
        chg = d.get("change","").strip()
        chg_str = f"{arrow} {chg}" if chg and chg not in ("0","—","") else "전일 동일"
        unavail = " idx-unavail" if d["value"] == "—" else ""
        date_html = f'<div class="idx-date">기준: {d["date"]}</div>' if d.get("date") else ""
        note_html = f'<div class="idx-note">{d["note"]}</div>' if d.get("note") else ""
        idx_html += f"""
      <a class="idx-card{unavail}" href="{d['url']}" target="_blank">
        <div class="idx-label">{d['label']}</div>
        <div class="idx-key">{key}</div>
        <div class="idx-val">{d['value']}</div>
        <div class="idx-chg {cls}">{chg_str}</div>
        {date_html}
        {note_html}
      </a>"""

    # 뉴스 블록
    source_order = ["TradeWinds","Splash247","Hellenic","구글뉴스"]
    grouped = {s: [] for s in source_order}
    for n in news:
        if n["source"] in grouped:
            grouped[n["source"]].append(n)

    news_html = ""
    for src in source_order:
        items = grouped[src]
        if not items:
            continue
        st = SOURCE_STYLE[src]
        src_url = SOURCE_URL[src]
        rows = ""
        for n in items:
            display = n.get("title_ko") or n["title"]
            display = display[:72] + ("…" if len(display) > 72 else "")
            # 구글뉴스는 언론사명을 label로 표시
            tag = f'<span class="news-src-tag">{n["label"]}</span>' if src == "구글뉴스" else ""
            rows += f"""
          <a class="news-row" href="{n['url']}" target="_blank" rel="noopener noreferrer">
            <span class="news-title">{tag}{display}</span>
            <span class="news-arrow">↗</span>
          </a>"""
        block_label = "구글 뉴스 (한국 해운)" if src == "구글뉴스" else items[0]['label']
        news_html += f"""
      <div class="news-block">
        <div class="src-header">
          <span class="src-flag">{st['flag']}</span>
          <a class="src-badge" href="{src_url}" target="_blank"
             style="color:{st['fg']};background:{st['bg']}">{block_label}</a>
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
.wrap{{max-width:960px;margin:0 auto;padding:2rem 1.25rem}}
.header{{display:flex;justify-content:space-between;align-items:flex-end;
         margin-bottom:1.75rem;padding-bottom:1rem;border-bottom:2px solid #2563eb}}
.brand-name{{font-size:1.5rem;font-weight:700;color:#1e3a8a;letter-spacing:-.5px}}
.brand-sub{{font-size:.8rem;color:#6b7280;margin-left:10px}}
.header-meta{{text-align:right;font-size:.78rem;color:#9ca3af;line-height:1.6}}
.sec-label{{font-size:.75rem;font-weight:600;text-transform:uppercase;
            letter-spacing:.8px;color:#6b7280;margin-bottom:.6rem}}
.idx-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:2rem}}
.idx-card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
           padding:1.1rem 1.25rem;text-decoration:none;color:inherit;
           transition:border-color .15s;display:block}}
.idx-card:hover{{border-color:#2563eb}}
.idx-card.idx-unavail{{opacity:.45}}
.idx-label{{font-size:.72rem;color:#9ca3af;margin-bottom:1px}}
.idx-key{{font-size:.72rem;font-weight:700;color:#6b7280;margin-bottom:.35rem}}
.idx-val{{font-size:1.7rem;font-weight:700;color:#111827}}
.idx-chg{{font-size:.82rem;margin-top:.3rem}}
.idx-date{{font-size:.7rem;color:#9ca3af;margin-top:.25rem}}
.idx-note{{font-size:.68rem;color:#d1d5db;margin-top:.15rem}}
.up{{color:#dc2626}}.dn{{color:#2563eb}}.neu{{color:#9ca3af}}
.news-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:2rem}}
.news-block{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}}
.src-header{{display:flex;align-items:center;gap:8px;padding:.65rem 1rem;
             border-bottom:1px solid #f3f4f6}}
.src-flag{{font-size:.9rem}}
.src-badge{{font-size:.73rem;font-weight:600;padding:2px 8px;border-radius:4px;
            text-decoration:none}}
.src-badge:hover{{opacity:.8}}
.news-rows{{display:flex;flex-direction:column}}
.news-row{{display:flex;align-items:center;justify-content:space-between;
           padding:.55rem 1rem;border-bottom:1px solid #f9fafb;
           text-decoration:none;color:inherit;gap:8px;transition:background .12s}}
.news-row:last-child{{border-bottom:none}}
.news-row:hover{{background:#f0f5ff}}
.news-title{{font-size:.82rem;line-height:1.45;color:#111827;flex:1}}
.news-src-tag{{font-size:.68rem;font-weight:600;color:#e65100;background:#fff3e0;
               padding:1px 5px;border-radius:3px;margin-right:5px;white-space:nowrap;flex-shrink:0}}
.news-arrow{{font-size:.8rem;color:#9ca3af;flex-shrink:0}}
.links-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:1.5rem}}
.link-card{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;
            padding:.75rem 1rem;text-decoration:none;color:inherit;transition:border-color .15s}}
.link-card:hover{{border-color:#2563eb}}
.link-card .lc-name{{font-size:.82rem;font-weight:600;color:#111827}}
.link-card .lc-sub{{font-size:.72rem;color:#9ca3af;margin-top:2px}}
.footer{{font-size:.72rem;color:#d1d5db;text-align:center;
         padding-top:.75rem;border-top:1px solid #e5e7eb}}
@media(max-width:640px){{
  .idx-grid{{grid-template-columns:1fr}}
  .news-grid{{grid-template-columns:1fr}}
  .links-grid{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div>
      <span class="brand-name">⚓ WaveDesk</span>
      <span class="brand-sub">해운 아침 브리핑</span>
    </div>
    <div class="header-meta">{DATE_STR}<br>업데이트 {TIME_STR} KST</div>
  </div>

  <div class="sec-label">📊 해운 시황 지수</div>
  <div class="idx-grid">{idx_html}
  </div>

  <div class="sec-label">📰 최신 해운 뉴스</div>
  <div class="news-grid">{news_html}
  </div>

  <div class="sec-label">🔗 주요 사이트</div>
  <div class="links-grid">
    <a class="link-card" href="https://www.ksg.co.kr/news/main_news.jsp" target="_blank">
      <div class="lc-name">코리아쉬핑가제트</div>
      <div class="lc-sub">국내 해운 전문 미디어</div>
    </a>
    <a class="link-card" href="https://www.shippingnewsnet.com/news/articleList.html?sc_sub_section_code=S2N1&view_type=sm" target="_blank">
      <div class="lc-name">쉬핑뉴스넷</div>
      <div class="lc-sub">국내 해운물류 뉴스</div>
    </a>
    <a class="link-card" href="https://www.shippingnewsnet.com/sdata/page.html?term=1" target="_blank">
      <div class="lc-name">쉬핑뉴스넷 해운지수</div>
      <div class="lc-sub">BDI · BCI · BPI · BSI</div>
    </a>
    <a class="link-card" href="https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000" target="_blank">
      <div class="lc-name">한국해양진흥공사 KCCI</div>
      <div class="lc-sub">한국 컨테이너 운임지수 (매주 월)</div>
    </a>
    <a class="link-card" href="https://www.nlic.go.kr/nlic/transInPortCt.action" target="_blank">
      <div class="lc-name">국가물류통합정보센터</div>
      <div class="lc-sub">SCFI · CCFI · BDI</div>
    </a>
    <a class="link-card" href="https://www.balticexchange.com/en/data/indices.html" target="_blank">
      <div class="lc-name">Baltic Exchange</div>
      <div class="lc-sub">BDI 공식 사이트</div>
    </a>
  </div>

  <div class="footer">
    WaveDesk · 매일 08:00 KST 자동 업데이트 · GitHub Pages 호스팅<br>
    BDI 출처: 쉬핑뉴스넷 · KCCI 출처: 한국해양진흥공사 · 해외 뉴스 제목은 Claude AI 번역
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

    idx_cnt = sum(1 for v in indices.values() if v["value"] != "—")
    print(f"  지수: {idx_cnt}개 수집")
    for k, v in indices.items():
        print(f"    {k}: {v['value']} {v.get('change','')}  ({v.get('date','')})")
    ko_cnt = sum(1 for n in news if n["source"] == "구글뉴스")
    print(f"  뉴스: 총 {len(news)}건 (국내 {ko_cnt}건)")

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
