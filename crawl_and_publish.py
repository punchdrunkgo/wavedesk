"""
WaveDesk - 해운 아침 브리핑
"""
import subprocess, sys, re, xml.etree.ElementTree as ET, json
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
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
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
        "BDI":   {"value": "—", "change": "", "label": "발틱운임지수",
                  "date": "", "url": "https://www.shippingnewsnet.com/sdata/page.html?term=1",
                  "note": "매일 · 쉬핑뉴스넷"},
        "KCCI":  {"value": "—", "change": "", "label": "한국컨운임지수",
                  "date": "", "url": "https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000",
                  "note": "매주 · 한국해양진흥공사"},
        "KDCI":  {"value": "—", "change": "", "label": "한국건화물선지수",
                  "date": "", "url": "https://www.kobc.or.kr/ebz/shippinginfo/kdci/gridList.do?mId=0301000000",
                  "note": "매일 · 한국해양진흥공사"},
        "NCFI":  {"value": "—", "change": "", "label": "닝보컨운임지수",
                  "date": "", "url": "https://www.kobc.or.kr/ebz/shippinginfo/ncfi/gridList.do?mId=0305000000",
                  "note": "매주 · 한국해양진흥공사"},
    }
    kcci_routes = []  # 노선별 세부 데이터
    kdci_routes = []
    ncfi_routes = []

    # BDI — 쉬핑뉴스넷
    try:
        r = requests.get("https://www.shippingnewsnet.com/sdata/page.html?term=1",
                         headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "lxml")
        rows = []
        for row in soup.select("table tr"):
            cols = [td.get_text(strip=True) for td in row.select("td")]
            if len(cols) >= 2 and re.match(r"\d{4}-\d{2}-\d{2}", cols[0]):
                rows.append(cols)
        if rows:
            l, p = rows[0], rows[1] if len(rows) > 1 else None
            chg = ""
            if p:
                try:
                    diff = int(l[1].replace(",","")) - int(p[1].replace(",",""))
                    chg = f"+{diff}" if diff >= 0 else str(diff)
                except Exception:
                    pass
            base["BDI"].update({"value": l[1], "change": chg, "date": l[0]})
    except Exception as e:
        print(f"  [BDI 오류] {e}")

    # KDCI — 한국해양진흥공사 (KDCI + CAPE/PANAMAX/SUPRAMAX/HANDY)
    try:
        r = requests.get("https://www.kobc.or.kr/ebz/shippinginfo/kdci/gridList.do?mId=0301000000",
                         headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "lxml")
        rows = []
        for row in soup.select("table tr"):
            cols = [td.get_text(strip=True) for td in row.select("td")]
            if len(cols) >= 6 and re.match(r"\d{4}-\d{2}-\d{2}", cols[0]):
                rows.append(cols)
        if rows:
            l, p = rows[0], rows[1] if len(rows) > 1 else None
            chg = ""
            if p:
                try:
                    diff = int(l[1].replace(",","")) - int(p[1].replace(",",""))
                    chg = f"+{diff}" if diff >= 0 else str(diff)
                except Exception:
                    pass
            base["KDCI"].update({"value": l[1], "change": chg, "date": l[0]})
            labels = ["CAPE","PANAMAX","SUPRAMAX","HANDY"]
            for i, name in enumerate(labels, start=2):
                if len(l) > i and p and len(p) > i:
                    try:
                        diff = int(l[i].replace(",","")) - int(p[i].replace(",",""))
                        pct = round(diff / int(p[i].replace(",","")) * 100, 2)
                        route_chg = f"+{pct}%" if pct >= 0 else f"{pct}%"
                    except Exception:
                        route_chg = ""
                    kdci_routes.append({"route": name, "value": l[i], "change": route_chg})
                elif len(l) > i:
                    kdci_routes.append({"route": name, "value": l[i], "change": ""})
    except Exception as e:
        print(f"  [KDCI 오류] {e}")

    # KCCI — 한국해양진흥공사 (종합 + 노선별)
    try:
        r = requests.get("https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000",
                         headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "lxml")
        for row in soup.select("table tr"):
            cols = [td.get_text(strip=True) for td in row.select("td")]
            n = len(cols)
            if n < 5:
                continue
            # 7컬럼(Group포함): Group(0) Code(1) Route(2) Weight(3) Cur(4) Prev(5) WkChg(6)
            # 6컬럼(Group없음):         Code(0) Route(1) Weight(2) Cur(3) Prev(4) WkChg(5)
            # 5컬럼(Group+Code없음):           Route(0) Weight(1) Cur(2) Prev(3) WkChg(4)
            if n >= 7:
                code, route, cur, prev, wk = cols[1], cols[2], cols[4], cols[5], cols[6]
            elif n == 6:
                code, route, cur, prev, wk = cols[0], cols[1], cols[3], cols[4], cols[5]
            elif n == 5:
                code, route, cur, prev, wk = "", cols[0], cols[2], cols[3], cols[4]
            else:
                continue

            def parse_chg(wk_str, cur_str, prev_str):
                m = re.search(r"\(([\+\-]?[\d.]+%)\)", wk_str)
                if not m:
                    return ""
                pct = m.group(1)
                if pct.startswith(("+","-")):
                    return pct
                try:
                    sign = "+" if float(cur_str.replace(",","")) >= float(prev_str.replace(",","")) else "-"
                    return sign + pct
                except Exception:
                    return pct

            if code == "KCCI":
                chg = parse_chg(wk, cur, prev)
                base["KCCI"].update({"value": cur, "change": chg, "date": NOW.strftime("%Y-%m-%d")})
            elif code and re.match(r"^[A-Z]{3,5}$", code) and cur and re.search(r"\d", cur):
                route_chg = parse_chg(wk, cur, prev)
                kcci_routes.append({"route": f"{route} ({code})", "value": cur, "change": route_chg})
    except Exception as e:
        print(f"  [KCCI 오류] {e}")

    # NCFI — 한국해양진흥공사 (종합 + 노선별)
    try:
        r = requests.get("https://www.kobc.or.kr/ebz/shippinginfo/ncfi/gridList.do?mId=0305000000",
                         headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "lxml")
        for row in soup.select("table tr"):
            cols = [td.get_text(strip=True) for td in row.select("td")]
            if len(cols) >= 4:
                route, cur, prev, wk = cols[0], cols[1], cols[2], cols[3]
                if not re.match(r"[\d.]+$", cur):
                    continue
                if route == "Composite Index":
                    base["NCFI"].update({"value": cur, "change": wk, "date": NOW.strftime("%Y-%m-%d")})
                elif route:
                    ncfi_routes.append({"route": route, "value": cur, "change": wk})
    except Exception as e:
        print(f"  [NCFI 오류] {e}")

    return base, kdci_routes, kcci_routes, ncfi_routes


# ══════════════════════════════════════════════════════════════════════════
# 2. 뉴스 수집
# ══════════════════════════════════════════════════════════════════════════

def fetch_google_news(query, lang, source, label, max_items=8):
    """Google 뉴스 RSS — 한/영 모두 지원, 해외 서버 차단 없음
    오늘/어제 기사만 필터링"""
    items = []
    try:
        if lang == "ko":
            url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
        else:
            url = f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        root = ET.fromstring(r.content)
        today = NOW.date()
        yesterday = (NOW - timedelta(days=1)).date()
        cutoff = NOW.replace(hour=0, minute=0, second=0) - timedelta(hours=12)  # 어제 오후 12시
        for item in root.findall(".//item")[:max_items * 2]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            src_el = item.find("source")
            lbl = src_el.text.strip() if src_el is not None else label
            if pub:
                try:
                    pub_dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc).astimezone(KST)
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass
            if title and link:
                items.append({"title": title, "title_ko": "" if lang == "en" else title,
                               "url": link, "source": source, "label": lbl})
            if len(items) >= max_items:
                break
    except Exception:
        pass
    return items


def gtranslate(text):
    """Google 번역 비공식 API — API 키 불필요"""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": text}
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = r.json()
        return "".join(seg[0] for seg in data[0] if seg[0])
    except Exception:
        return text


def translate_titles(news_list):
    """해외 뉴스 제목 Google 번역 (API 키 불필요)"""
    foreign = [n for n in news_list if n["source"] == "해외뉴스" and not n["title_ko"]]
    for n in foreign:
        n["title_ko"] = gtranslate(n["title"])
    return news_list


def get_news():
    news = []
    # 해외 — Google 뉴스 영어 RSS
    en_queries = [
        ("shipping freight rates", 4),
        ("container shipping market", 3),
        ("bulk carrier tanker shipping", 2),
        ("maritime industry news", 3),
    ]
    for q, cnt in en_queries:
        got = fetch_google_news(q.replace(" ","+"), "en", "해외뉴스", "Shipping News", cnt)
        news += got

    # 국내 — 핵심 해운 (우선순위 높음)
    ko_core = [
        ("해운+운임", 5),
        ("해운+물류+컨테이너", 4),
        ("벌크선+탱커+해운", 3),
        ("컨테이너선+운임", 3),
        ("해상운임+물동량", 3),
    ]
    # 국내 — 관련 분야 (선박·조선·수산·원양 등)
    ko_related = [
        ("조선+선박+수주", 3),
        ("원양어선+수산", 2),
        ("LNG선+벙커링", 2),
        ("항만+물류+수출", 2),
        ("선사+해운사", 2),
    ]
    for q, cnt in ko_core + ko_related:
        got = fetch_google_news(q, "ko", "구글뉴스", "국내뉴스", cnt)
        news += got

    seen, result = set(), []
    for n in news:
        key = n["title"][:25]
        if key not in seen:
            seen.add(key)
            result.append(n)

    result = translate_titles(result)
    return result


# ══════════════════════════════════════════════════════════════════════════
# 3. HTML 생성
# ══════════════════════════════════════════════════════════════════════════

SOURCE_STYLE = {
    "해외뉴스": {"bg": "#e8f0fe", "fg": "#1a56db", "flag": "🌐"},
    "구글뉴스": {"bg": "#fff3e0", "fg": "#e65100", "flag": "🇰🇷"},
}
SOURCE_URL = {
    "해외뉴스": "https://news.google.com/search?q=shipping+freight&hl=en&gl=US&ceid=US:en",
    "구글뉴스": "https://news.google.com/search?q=해운+운임&hl=ko&gl=KR&ceid=KR:ko",
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


def build_html(indices, kdci_routes, kcci_routes, ncfi_routes, news):
    # 지수 카드 (종합지수 4개)
    idx_html = ""
    for key, d in indices.items():
        cls, arrow = dir_cls(d.get("change",""))
        chg = d.get("change","").strip()
        chg_str = f"{arrow} {chg}" if chg and chg not in ("0","—","") else "전일 동일"
        unavail = " idx-unavail" if d["value"] == "—" else ""
        date_label = d.get("date") or NOW.strftime("%Y-%m-%d") + " 조회"
        date_html = f'<div class="idx-date">기준: {date_label}</div>'
        note_html = f'<div class="idx-note">{d["note"]}</div>' if d.get("note") else ""
        idx_html += f"""
      <a class="idx-card{unavail}" href="{d['url']}" target="_blank">
        <div class="idx-label">{d['label']}</div>
        <div class="idx-key">{key}</div>
        <div class="idx-val">{d['value']}</div>
        <div class="idx-chg {cls}">{chg_str}</div>
        {date_html}{note_html}
      </a>"""

    # 세부 노선 아코디언 (KDCI/KCCI/NCFI)
    def accordion_html(aid, title, routes, unit, src_url):
        if not routes:
            return ""
        rows = ""
        for r in routes:
            chg = r.get("change","")
            cls, arrow = dir_cls(chg)
            chg_html = f'<span class="acc-chg {cls}">{arrow} {chg}</span>' if chg else ""
            rows += (f'<div class="acc-row">'
                     f'<span class="acc-route">{r["route"]}</span>'
                     f'<span class="acc-val">{r["value"]}{unit}{chg_html}</span>'
                     f'</div>')
        return f"""<div class="accordion">
        <div class="acc-header">
          <button class="acc-toggle" data-target="{aid}">
            {title} <span class="acc-arrow">▾</span>
          </button>
          <a class="acc-link-btn" href="{src_url}" target="_blank">📊</a>
        </div>
        <div class="acc-body" id="{aid}">
          <div class="acc-rows">{rows}</div>
        </div>
      </div>"""

    accordions_html = (
        accordion_html("acc-kdci", "KDCI 건화물선", kdci_routes, " pt",
                       "https://www.kobc.or.kr/ebz/shippinginfo/kdci/gridList.do?mId=0301000000") +
        accordion_html("acc-kcci", "KCCI 컨테이너 노선별", kcci_routes, " pt",
                       "https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000") +
        accordion_html("acc-ncfi", "NCFI 닝보 노선별", ncfi_routes, " pt",
                       "https://www.kobc.or.kr/ebz/shippinginfo/ncfi/gridList.do?mId=0305000000")
    )

    # 뉴스: 좌=국내(구글뉴스) / 우=해외
    ko_news = [n for n in news if n["source"] == "구글뉴스"][:8]
    en_news = [n for n in news if n["source"] == "해외뉴스"][:8]

    def news_rows_html(items, show_tag=False):
        rows = ""
        for n in items:
            display = n.get("title_ko") or n["title"]
            display = display[:72] + ("…" if len(display) > 72 else "")
            tag = f'<span class="news-src-tag">{n["label"]}</span>' if show_tag else ""
            rows += f"""
          <a class="news-row" href="{n['url']}" target="_blank" rel="noopener noreferrer">
            <span class="news-title">{tag}{display}</span>
            <span class="news-arrow">↗</span>
          </a>"""
        return rows

    en_blocks = news_rows_html(en_news, show_tag=True)

    news_html = f"""
      <div class="news-col">
        <div class="news-col-header">
          <span class="flag">📍</span> 국내 해운 뉴스
        </div>
        <div class="news-inner">
          {news_rows_html(ko_news, show_tag=True)}
        </div>
      </div>
      <div class="news-col">
        <div class="news-col-header">
          <span class="flag">🌐</span> 해외 해운 뉴스
        </div>
        <div class="news-inner">
          {en_blocks}
        </div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WaveDesk · 해운 아침 브리핑</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚓</text></svg>">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans KR',sans-serif;
      background:#f0f4f8;color:#1a1a2e;min-height:100vh}}
.wrap{{max-width:1100px;margin:0 auto;padding:1.5rem 1.25rem}}

/* 헤더 */
.header{{display:flex;justify-content:space-between;align-items:center;
         margin-bottom:1rem;padding-bottom:.6rem;border-bottom:2px solid #2563eb}}
.brand{{display:flex;align-items:baseline;gap:8px}}
.brand-name{{font-size:1.15rem;font-weight:700;color:#1e3a8a;letter-spacing:-.5px}}
.brand-sub{{font-size:.75rem;color:#6b7280}}
.header-time{{font-size:.78rem;color:#9ca3af;text-align:right;line-height:1.6}}

/* 섹션 라벨 */
.sec-label{{font-size:.75rem;font-weight:600;text-transform:uppercase;
            letter-spacing:.8px;color:#6b7280;margin-bottom:.5rem}}

/* 지수 카드 (4열) */
.idx-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:.75rem}}
.idx-card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
           padding:.9rem 1.1rem;text-decoration:none;color:inherit;
           transition:border-color .15s;display:block}}
.idx-card:hover{{border-color:#2563eb}}
.idx-card.idx-unavail{{opacity:.45}}
.idx-label{{font-size:.7rem;color:#9ca3af;margin-bottom:1px}}
.idx-key{{font-size:.7rem;font-weight:700;color:#6b7280;margin-bottom:.3rem}}
.idx-val{{font-size:1.5rem;font-weight:700;color:#111827}}
.idx-chg{{font-size:.78rem;margin-top:.3rem}}
.idx-date{{font-size:.68rem;color:#9ca3af;margin-top:.2rem}}
.idx-note{{font-size:.65rem;color:#d1d5db;margin-top:.1rem}}
.up{{color:#dc2626}}.dn{{color:#2563eb}}.neu{{color:#9ca3af}}

/* 아코디언 (3열 드롭다운) */
.acc-wrap{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:.75rem}}
.accordion{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden}}
.acc-header{{display:flex;justify-content:space-between;align-items:center;
             padding:.5rem .75rem;background:#f8faff;border-bottom:1px solid #e5e7eb}}
.acc-toggle{{background:none;border:none;cursor:pointer;font-size:.78rem;
             font-weight:600;color:#374151;font-family:inherit;padding:0;text-align:left}}
.acc-toggle:hover{{color:#2563eb}}
.acc-arrow{{transition:transform .2s;color:#9ca3af;font-size:.72rem;margin-left:3px}}
.acc-toggle.open .acc-arrow{{transform:rotate(180deg)}}
.acc-link-btn{{font-size:.7rem;padding:2px 8px;border:1px solid #2563eb;
               border-radius:4px;color:#2563eb;text-decoration:none;white-space:nowrap}}
.acc-link-btn:hover{{background:#2563eb;color:#fff}}
.acc-body{{max-height:0;overflow:hidden;transition:max-height .3s ease}}
.acc-body.open{{max-height:300px;overflow-y:auto}}
.acc-rows{{display:flex;flex-direction:column}}
.acc-row{{display:flex;justify-content:space-between;align-items:center;
          padding:.32rem .75rem;border-bottom:1px solid #f3f4f6}}
.acc-row:last-child{{border-bottom:none}}
.acc-route{{font-size:.72rem;color:#6b7280}}
.acc-val{{font-size:.75rem;font-weight:600;color:#111827}}
.acc-chg{{font-size:.7rem;font-weight:500;margin-left:5px}}
.acc-chg.up{{color:#dc2626}}.acc-chg.dn{{color:#2563eb}}.acc-chg.neu{{color:#9ca3af}}

/* 지수 탭 (운임지수/연료환경/통계) */
.idx-tab-bar{{display:flex;gap:5px;margin-bottom:7px}}
.idx-tab{{padding:4px 13px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;
          font-size:.75rem;font-weight:600;color:#6b7280;cursor:pointer;font-family:inherit}}
.idx-tab.active{{background:#2563eb;color:#fff;border-color:#2563eb}}
.idx-tab:hover:not(.active){{border-color:#2563eb;color:#2563eb}}
.idx-tab-panel{{display:none;flex-wrap:wrap;gap:7px;margin-bottom:1.25rem}}
.idx-tab-panel.active{{display:flex}}
.idx-link-btn{{font-size:.72rem;padding:4px 10px;border-radius:5px;
               border:1px solid #e5e7eb;background:#fff;color:#374151;
               text-decoration:none;transition:border-color .15s;white-space:nowrap}}
.idx-link-btn:hover{{border-color:#2563eb;color:#1e3a8a}}

/* 뉴스 */
.news-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:1.5rem}}
.news-col{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}}
.news-col-header{{display:flex;align-items:center;gap:6px;padding:.65rem 1rem;
                  background:#f8faff;border-bottom:1px solid #e5e7eb;
                  font-size:.8rem;font-weight:600;color:#1e3a8a}}
.news-inner{{display:flex;flex-direction:column;max-height:330px;overflow-y:auto}}
.src-mini-header{{padding:.3rem 1rem;background:#f9fafb;
                  font-size:.68rem;color:#9ca3af;border-bottom:1px solid #f3f4f6}}
.news-row{{display:flex;align-items:center;justify-content:space-between;
           padding:.5rem 1rem;border-bottom:1px solid #f9fafb;
           text-decoration:none;color:inherit;gap:8px;transition:background .12s}}
.news-row:last-child{{border-bottom:none}}
.news-row:hover{{background:#f0f5ff}}
.news-title{{font-size:.81rem;line-height:1.45;color:#111827;flex:1}}
.news-src-tag{{font-size:.67rem;font-weight:600;color:#e65100;background:#fff3e0;
               padding:1px 5px;border-radius:3px;margin-right:5px;
               white-space:nowrap;flex-shrink:0}}
.news-arrow{{font-size:.8rem;color:#9ca3af;flex-shrink:0}}

/* 사이트 섹션 */
.sites-section{{margin-bottom:1rem}}

/* ＋ 뱃지 */
.pin-dot{{display:inline-flex;align-items:center;justify-content:center;
          width:16px;height:16px;border-radius:50%;
          background:#e5e7eb;color:#6b7280;font-size:.6rem;font-weight:700;
          cursor:pointer;margin-left:4px;line-height:1;
          transition:background .12s,color .12s;
          user-select:none;vertical-align:middle;flex-shrink:0}}
.pin-dot:hover{{background:#0071e3;color:#fff}}
.pin-dot.pinned{{background:#0071e3;color:#fff}}

/* 사이트 그룹 */
.site-group-label{{font-size:.68rem;font-weight:600;color:#86868b;
                   text-transform:uppercase;letter-spacing:.6px;
                   margin:1rem 0 .4rem;padding-left:2px}}
.site-link-row{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:.25rem}}
.site-link-item{{display:inline-flex;align-items:center;
                 font-size:.78rem;padding:5px 11px;border-radius:980px;
                 border:1px solid #d2d2d7;background:#fff;color:#1d1d1f;
                 cursor:default;transition:border-color .12s,background .12s;
                 font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Noto Sans KR',sans-serif;
                 line-height:1.4}}
.site-link-item a{{color:inherit;text-decoration:none;pointer-events:all;cursor:pointer}}
.site-link-item:hover{{border-color:#0071e3;background:#f5f5f7}}
.site-link-item.dragging{{opacity:.4}}

/* 내 사이트 */
.my-site-section{{margin-bottom:.75rem}}
.my-site-header{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
.my-site-label{{font-size:.82rem;font-weight:600;color:#1d1d1f;
                font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Noto Sans KR',sans-serif}}
.my-site-hint{{font-size:.67rem;color:#86868b;flex:1}}
.my-site-grid{{display:flex;flex-wrap:wrap;gap:6px;min-height:40px;
               padding:8px 10px;border-radius:12px;
               border:1.5px dashed #d2d2d7;background:#fafafa;
               margin-bottom:.5rem;transition:border-color .12s,background .12s}}
.my-site-grid.drag-active{{border-color:#0071e3;background:#f0f6ff}}
.my-empty{{font-size:.73rem;color:#86868b;align-self:center;padding:.25rem 0}}
.my-site-item{{display:inline-flex;align-items:center;gap:5px;
               font-size:.78rem;padding:5px 12px;border-radius:7px;
               border:none;background:#0071e3;color:#fff;
               cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Noto Sans KR',sans-serif;
               line-height:1.4;text-decoration:none;
               transition:background .12s}}
.my-site-item:hover{{background:#0077ed}}
.my-site-item a{{color:inherit;text-decoration:none;pointer-events:all}}
.my-del-btn{{font-size:.65rem;color:rgba(255,255,255,.7);background:none;border:none;
             cursor:pointer;padding:0;line-height:1;pointer-events:all}}
.my-del-btn:hover{{color:#fff}}

/* 주요 사이트 카드 */
.site-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:.75rem}}
.site-card{{background:#fff;border:1px solid #d2d2d7;border-radius:12px;
            padding:.7rem 1rem;text-decoration:none;color:inherit;
            transition:border-color .12s,box-shadow .12s;display:block}}
.site-card:hover{{border-color:#0071e3;box-shadow:0 2px 8px rgba(0,113,227,.1)}}
.site-card-name{{font-size:.82rem;font-weight:500;color:#1d1d1f}}
.site-card-sub{{font-size:.68rem;color:#86868b;margin-top:2px}}
.site-category{{font-size:.68rem;font-weight:600;text-transform:uppercase;
                letter-spacing:.5px;color:#86868b;margin:.65rem 0 .3rem}}

/* SM 계열사 */
.aff-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.aff-card{{background:#1e3a8a;border-radius:12px;padding:.65rem 1rem;
           text-decoration:none;transition:background .12s}}
.aff-card:hover{{background:#1a56db}}
.aff-name{{font-size:.8rem;font-weight:500;color:#fff}}
.aff-desc{{font-size:.68rem;color:#93c5fd;margin-top:2px}}

/* 직접 추가 버튼 */
.direct-add-btn{{display:inline-flex;align-items:center;gap:5px;
                 font-size:.78rem;padding:6px 14px;border-radius:980px;
                 border:1px solid #d2d2d7;background:#fff;color:#0071e3;
                 cursor:pointer;font-family:inherit;
                 transition:border-color .12s,background .12s}}
.direct-add-btn:hover{{border-color:#0071e3;background:#f0f6ff}}

/* 모달 */
.modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);
                z-index:100;align-items:center;justify-content:center}}
.modal-overlay.open{{display:flex}}
.modal-box{{background:#fff;border-radius:18px;padding:1.5rem;width:300px;max-width:90vw;
            box-shadow:0 8px 32px rgba(0,0,0,.15)}}
.modal-title{{font-size:.92rem;font-weight:600;color:#1d1d1f;margin-bottom:.9rem}}
.modal-input{{width:100%;padding:.6rem .9rem;border:1px solid #d2d2d7;border-radius:8px;
              font-size:.82rem;margin-bottom:.55rem;font-family:inherit;background:#fff;color:#1d1d1f}}
.modal-input:focus{{outline:none;border-color:#0071e3}}
.modal-btns{{display:flex;gap:7px;margin-top:.4rem}}
.modal-btn{{flex:1;padding:.55rem;border-radius:8px;border:none;
            font-size:.8rem;font-weight:600;cursor:pointer;font-family:inherit}}
.modal-btn-cancel{{background:#f5f5f7;color:#1d1d1f}}
.modal-btn-save{{background:#0071e3;color:#fff}}

.my-add-btn{{display:none}} /* 상단 직접추가 버튼 숨김 */

.footer{{font-size:.72rem;color:#d1d5db;text-align:center;
         padding-top:.75rem;border-top:1px solid #e5e7eb}}

@media(max-width:700px){{
  .idx-grid{{grid-template-columns:repeat(2,1fr)}}
  .acc-wrap{{grid-template-columns:1fr}}
  .news-grid{{grid-template-columns:1fr}}
  .site-grid{{grid-template-columns:repeat(2,1fr)}}
  .aff-grid{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="brand">
      <span class="brand-name">⚓ WaveDesk</span>
      <span class="brand-sub">해운 아침 브리핑</span>
    </div>
    <div class="header-time">{DATE_STR}<br>업데이트 {TIME_STR} KST</div>
  </div>

  <div class="sec-label">📊 해운 시황 지수</div>
  <div class="idx-grid">{idx_html}
  </div>

  <div class="acc-wrap">
    {accordions_html}
  </div>

  <!-- 내 사이트 (뉴스 위) -->
  <div class="my-site-header">
    <span class="my-site-label">⭐ 내 사이트</span>
    <span class="my-site-hint">아래 ＋ 클릭으로 추가 · 항목 클릭으로 이동 · 이 브라우저에만 저장</span>
  </div>
  <div class="my-site-grid droptarget" id="mySiteGrid">
    <div class="my-empty" id="myEmpty">아래 섹션의 ＋ 버튼을 클릭해서 추가하세요</div>
  </div>

  <div class="sec-label">📰 최신 해운 뉴스</div>
  <div class="news-grid">
    {news_html}
  </div>

  <div class="sites-section">
    <div class="sec-label">🔗 주요 사이트</div>

    <!-- 운임지수 -->
    <div class="site-group-label">📈 운임지수</div>
    <div class="site-link-row" id="group-idx">
      <div class="site-link-item draggable" draggable="true" data-name="SCFI·KCCI·CCFI — surff.kr" data-url="https://surff.kr/indices"><a href="https://surff.kr/indices" target="_blank">SCFI·KCCI·CCFI — surff.kr</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="SCFI·CCFI·BDI — 국가물류통합정보센터" data-url="https://nlic.go.kr/nlic/ocnStatisticBoard.action"><a href="https://nlic.go.kr/nlic/ocnStatisticBoard.action" target="_blank">SCFI·CCFI·BDI — 국가물류통합정보센터</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="BDI·BCI·BPI — 쉬핑뉴스넷" data-url="https://www.shippingnewsnet.com/sdata/page.html?term=1"><a href="https://www.shippingnewsnet.com/sdata/page.html?term=1" target="_blank">BDI·BCI·BPI — 쉬핑뉴스넷</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="KCCI — 한국해양진흥공사" data-url="https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000"><a href="https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000" target="_blank">KCCI — 한국해양진흥공사</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="Baltic Exchange" data-url="https://www.balticexchange.com/en/index.html"><a href="https://www.balticexchange.com/en/index.html" target="_blank">Baltic Exchange</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="SCFI — 상하이해운거래소" data-url="https://en.sse.net.cn/indices/scfinew.jsp"><a href="https://en.sse.net.cn/indices/scfinew.jsp" target="_blank">SCFI — 상하이해운거래소</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="CCFI — 상하이해운거래소" data-url="https://en.sse.net.cn/indices/ccfinew.jsp"><a href="https://en.sse.net.cn/indices/ccfinew.jsp" target="_blank">CCFI — 상하이해운거래소</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="Freightos FBX" data-url="https://www.freightos.com/enterprise/terminal/freightos-baltic-index-global-container-pricing-index/"><a href="https://www.freightos.com/enterprise/terminal/freightos-baltic-index-global-container-pricing-index/" target="_blank">Freightos FBX</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="TradLinx 종합 차트" data-url="https://www.tradlinx.com/ko/freight-index"><a href="https://www.tradlinx.com/ko/freight-index" target="_blank">TradLinx 종합 차트</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="탱커 TCE·Worldscale" data-url="https://www.spotmarketcap.com/shipping"><a href="https://www.spotmarketcap.com/shipping" target="_blank">탱커 TCE·Worldscale</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
    </div>

    <!-- 연료·환경 -->
    <div class="site-group-label">⛽ 연료·환경</div>
    <div class="site-link-row" id="group-env">
      <div class="site-link-item draggable" draggable="true" data-name="글로벌 벙커유 — Ship&Bunker" data-url="https://shipandbunker.com/prices"><a href="https://shipandbunker.com/prices" target="_blank">⛽ 글로벌 벙커유 — Ship&Bunker</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="EU-ETS 탄소배출권" data-url="https://shipandbunker.com/prices/ea/eu/eu-eua"><a href="https://shipandbunker.com/prices/ea/eu/eu-eua" target="_blank">💶 EU-ETS 탄소배출권</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="LNG 스팟 — LNG Prime" data-url="https://lngprime.com/"><a href="https://lngprime.com/" target="_blank">🔥 LNG 스팟 — LNG Prime</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="EUA 과거 가격" data-url="https://kr.investing.com/commodities/carbon-emissions-historical-data"><a href="https://kr.investing.com/commodities/carbon-emissions-historical-data" target="_blank">📉 EUA 과거 가격</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="JKM LNG 스팟" data-url="https://kr.investing.com/commodities/lng-japan-korea-marker-platts-futures"><a href="https://kr.investing.com/commodities/lng-japan-korea-marker-platts-futures" target="_blank">🌊 JKM LNG 스팟</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="벌크선 운영비·신조가" data-url="https://www.balticexchange.com/en/data-services/market-information0/indices.html"><a href="https://www.balticexchange.com/en/data-services/market-information0/indices.html" target="_blank">📋 벌크선 운영비·신조가</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
    </div>

    <!-- 통계·보고서 -->
    <div class="site-group-label">📊 통계·보고서</div>
    <div class="site-link-row" id="group-stat">
      <div class="site-link-item draggable" draggable="true" data-name="해상 운송 통계" data-url="https://nlic.go.kr/nlic/seaStatisticBoard.action"><a href="https://nlic.go.kr/nlic/seaStatisticBoard.action" target="_blank">🚢 해상 운송 통계</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="KOBC 일간 건화물선 보고서" data-url="https://www.kobc.or.kr/ebz/shippinginfo/reportDaily/list.do?mId=0201000000"><a href="https://www.kobc.or.kr/ebz/shippinginfo/reportDaily/list.do?mId=0201000000" target="_blank">📄 KOBC 일간 건화물선 보고서</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="KOBC 주간통합 보고서" data-url="https://www.kobc.or.kr/ebz/shippinginfo/reportWeekly/view.do?mId=0202000000"><a href="https://www.kobc.or.kr/ebz/shippinginfo/reportWeekly/view.do?mId=0202000000" target="_blank">📄 KOBC 주간통합 보고서</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="KDCI 세부지수" data-url="https://www.kobc.or.kr/ebz/shippinginfo/kdci/gridList.do?mId=0301000000"><a href="https://www.kobc.or.kr/ebz/shippinginfo/kdci/gridList.do?mId=0301000000" target="_blank">📊 KDCI 세부지수</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
      <div class="site-link-item draggable" draggable="true" data-name="NCFI 닝보 노선별" data-url="https://www.kobc.or.kr/ebz/shippinginfo/ncfi/gridList.do?mId=0305000000"><a href="https://www.kobc.or.kr/ebz/shippinginfo/ncfi/gridList.do?mId=0305000000" target="_blank">📊 NCFI 닝보 노선별</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
    </div>

    <!-- 주요 해운 사이트 - 국내/해외 신문만 -->
    <div class="site-group-label">📰 주요 해운 사이트</div>
    <div class="site-grid">
      <a class="site-card" href="https://www.ksg.co.kr/news/main_news.jsp" target="_blank">
        <div class="site-card-name">코리아쉬핑가제트</div><div class="site-card-sub">국내 해운 전문 미디어</div></a>
      <a class="site-card" href="https://www.shippingnewsnet.com/news/articleList.html?sc_sub_section_code=S2N1&view_type=sm" target="_blank">
        <div class="site-card-name">쉬핑뉴스넷</div><div class="site-card-sub">국내 해운물류 뉴스</div></a>
      <a class="site-card" href="http://www.maritimepress.co.kr/" target="_blank">
        <div class="site-card-name">한국해운신문</div><div class="site-card-sub">해운·조선·항만물류</div></a>
      <a class="site-card" href="https://www.klnews.co.kr/" target="_blank">
        <div class="site-card-name">물류신문</div><div class="site-card-sub">물류 전문 매체</div></a>
      <a class="site-card" href="https://maritime-executive.com/" target="_blank">
        <div class="site-card-name">Maritime Executive</div><div class="site-card-sub">해외 해운 전문 (영문)</div></a>
      <a class="site-card" href="https://splash247.com/" target="_blank">
        <div class="site-card-name">Splash247</div><div class="site-card-sub">해외 해운 뉴스 (영문)</div></a>
    </div>

    <!-- 직접 추가 버튼 - 주요 사이트와 SM 계열사 사이 -->
    <div style="margin:.75rem 0;padding:.65rem 0;border-top:1px solid #f3f4f6;border-bottom:1px solid #f3f4f6;display:flex;align-items:center;gap:10px">
      <button class="direct-add-btn" id="addSiteBtn">＋ 내 사이트에 직접 추가</button>
      <span style="font-size:.67rem;color:#86868b">URL을 직접 입력해서 내 사이트에 추가하세요</span>
    </div>

    <!-- SM 계열사 -->
    <div class="site-group-label">🚢 SM그룹 해운 계열사</div>
    <div class="aff-grid">
      <a class="aff-card" href="http://www.korealines.co.kr" target="_blank">
        <div class="aff-name">대한해운</div><div class="aff-desc">전용선 · 벌크 · 탱커</div></a>
      <a class="aff-card" href="https://www.smlines.com/kr/" target="_blank">
        <div class="aff-name">SM상선</div><div class="aff-desc">컨테이너 전문 선사</div></a>
      <a class="aff-card" href="http://www.smksc.co.kr/" target="_blank">
        <div class="aff-name">대한상선</div><div class="aff-desc">벌크 · 종합자원 수송</div></a>
      <a class="aff-card" href="https://klclng.com/" target="_blank">
        <div class="aff-name">대한해운LNG</div><div class="aff-desc">LNG 전문 운송</div></a>
      <a class="aff-card" href="https://www.klcsm.co.kr/" target="_blank">
        <div class="aff-name">KLCSM</div><div class="aff-desc">선박관리 · 수리</div></a>
      <a class="aff-card" href="http://www.cmship.co.kr/" target="_blank">
        <div class="aff-name">창명해운</div><div class="aff-desc">벌크 · 특수화물</div></a>
      <a class="aff-card" href="http://www.smlgi.co.kr/index" target="_blank">
        <div class="aff-name">SM상선 경인터미널</div><div class="aff-desc">항만 · 물류 서비스</div></a>
      <a class="aff-card" href="http://www.smlgp.co.kr/index" target="_blank">
        <div class="aff-name">SM상선 김포터미널</div><div class="aff-desc">항만 · 내륙물류</div></a>
      <a class="aff-card" href="https://www.smgroup.co.kr/business/shipping-industry.do" target="_blank">
        <div class="aff-name">SM그룹 (해운부문)</div><div class="aff-desc">그룹 공식 홈페이지</div></a>
    </div>
  </div>

  <div id="addLinkModal" class="modal-overlay">
    <div class="modal-box">
      <div class="modal-title">사이트 추가</div>
      <input id="newLinkName" class="modal-input" placeholder="사이트 이름">
      <input id="newLinkUrl" class="modal-input" placeholder="URL (https://...)">
      <div class="modal-btns">
        <button id="cancelLinkBtn" class="modal-btn modal-btn-cancel">취소</button>
        <button id="saveLinkBtn" class="modal-btn modal-btn-save">추가</button>
      </div>
    </div>
  </div>

  <div class="footer">
    {DATE_STR} · {TIME_STR} KST &nbsp;|&nbsp; WaveDesk · 매일 08:00 자동 업데이트 · GitHub Pages
  </div>

</div>

<script>
(function() {{
  // ── 아코디언 (하나 열면 전부 열림)
  document.querySelectorAll('.acc-toggle').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const allBodies = document.querySelectorAll('.acc-body');
      const allBtns = document.querySelectorAll('.acc-toggle');
      const isOpen = document.getElementById(btn.dataset.target).classList.contains('open');
      if (isOpen) {{
        allBodies.forEach(b => b.classList.remove('open'));
        allBtns.forEach(b => b.classList.remove('open'));
      }} else {{
        allBodies.forEach(b => b.classList.add('open'));
        allBtns.forEach(b => b.classList.add('open'));
      }}
    }});
  }});

  // ── 내 사이트 드래그앤드롭
  const MY_KEY = 'wavedesk_my_sites_v3';
  const myGrid = document.getElementById('mySiteGrid');
  const myEmpty = document.getElementById('myEmpty');

  function getMyLinks() {{
    try {{ return JSON.parse(localStorage.getItem(MY_KEY)) || []; }}
    catch(e) {{ return []; }}
  }}
  function saveMyLinks(links) {{ localStorage.setItem(MY_KEY, JSON.stringify(links)); }}

  let dragData = null; // {{name, url, fromMy: bool, fromIdx: int}}

  function renderMy() {{
    myGrid.querySelectorAll('.my-site-item').forEach(el => el.remove());
    const links = getMyLinks();
    myEmpty.style.display = links.length ? 'none' : 'flex';
    links.forEach((l, i) => {{
      const el = document.createElement('a');
      el.className = 'my-site-item';
      el.href = l.url;
      el.target = '_blank';
      el.rel = 'noopener noreferrer';
      el.draggable = true;
      el.innerHTML = `${{l.name}}<button class="my-del-btn" title="삭제" tabindex="-1">×</button>`;
      el.querySelector('.my-del-btn').onclick = (e) => {{
        e.preventDefault(); e.stopPropagation();
        const updated = getMyLinks(); updated.splice(i, 1); saveMyLinks(updated); renderMy(); updatePinDots();
      }};
      // 내 사이트 간 드래그 (순서 변경)
      el.addEventListener('dragstart', e => {{
        dragData = {{name: l.name, url: l.url, fromMy: true, fromIdx: i}};
        el.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      }});
      el.addEventListener('dragend', () => el.classList.remove('dragging'));
      el.addEventListener('dragover', e => {{ e.preventDefault(); }});
      el.addEventListener('drop', e => {{
        e.preventDefault(); e.stopPropagation();
        if (!dragData || !dragData.fromMy || dragData.fromIdx === i) return;
        const updated = getMyLinks();
        const [moved] = updated.splice(dragData.fromIdx, 1);
        updated.splice(i, 0, moved);
        saveMyLinks(updated); dragData = null; renderMy();
      }});
      myGrid.appendChild(el);
    }});
  }}

  // 내 사이트 드롭존 이벤트
  myGrid.addEventListener('dragover', e => {{
    e.preventDefault(); myGrid.classList.add('drag-active');
  }});
  myGrid.addEventListener('dragleave', () => myGrid.classList.remove('drag-active'));
  myGrid.addEventListener('drop', e => {{
    e.preventDefault(); myGrid.classList.remove('drag-active');
    if (!dragData || dragData.fromMy) return; // 내 사이트 간 이동은 위에서 처리
    const links = getMyLinks();
    if (!links.find(l => l.url === dragData.url)) {{
      links.push({{name: dragData.name, url: dragData.url}});
      saveMyLinks(links); renderMy();
    }}
    dragData = null;
  }});

  // ── pin-dot 클릭: 내 사이트 추가/제거
  function updatePinDots() {{
    const links = getMyLinks();
    const urls = new Set(links.map(l => l.url));
    document.querySelectorAll('.pin-dot').forEach(dot => {{
      const item = dot.closest('.site-link-item');
      if (!item) return;
      const url = item.dataset.url;
      dot.classList.toggle('pinned', urls.has(url));
      dot.title = urls.has(url) ? '내 사이트에서 제거' : '내 사이트에 추가';
    }});
  }}

  document.querySelectorAll('.pin-dot').forEach(dot => {{
    dot.addEventListener('click', e => {{
      e.stopPropagation();
      const item = dot.closest('.site-link-item');
      if (!item) return;
      const {{name, url}} = item.dataset;
      const links = getMyLinks();
      const idx = links.findIndex(l => l.url === url);
      if (idx >= 0) {{ links.splice(idx, 1); }}
      else {{ links.push({{name, url}}); }}
      saveMyLinks(links); renderMy(); updatePinDots();
    }});
  }});

  // site-link-item 더블클릭: 내 사이트에서 제거
  document.querySelectorAll('.site-link-item.draggable').forEach(item => {{
    item.addEventListener('dblclick', () => {{
      const links = getMyLinks();
      const idx = links.findIndex(l => l.url === item.dataset.url);
      if (idx >= 0) {{
        links.splice(idx, 1); saveMyLinks(links); renderMy(); updatePinDots();
      }}
    }});
    item.addEventListener('dragstart', e => {{
      dragData = {{name: item.dataset.name, url: item.dataset.url, fromMy: false}};
      item.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'copy';
    }});
    item.addEventListener('dragend', () => item.classList.remove('dragging'));
  }});

  renderMy(); updatePinDots();
  const addBtn = document.getElementById('addSiteBtn');
  const modal = document.getElementById('addLinkModal');
  const cancelBtn = document.getElementById('cancelLinkBtn');
  const saveBtn = document.getElementById('saveLinkBtn');
  const nameInput = document.getElementById('newLinkName');
  const urlInput = document.getElementById('newLinkUrl');

  if (addBtn) addBtn.onclick = () => {{ modal.classList.add('open'); nameInput.focus(); }};
  if (cancelBtn) cancelBtn.onclick = () => {{
    modal.classList.remove('open'); nameInput.value = ''; urlInput.value = '';
  }};
  if (saveBtn) saveBtn.onclick = () => {{
    let name = nameInput.value.trim();
    let url = urlInput.value.trim();
    if (!url) return;
    if (!/^https?:\\/\\//.test(url)) url = 'https://' + url;
    if (!name) name = url.replace(/^https?:\\/\\//, '').split('/')[0];
    const links = getMyLinks(); links.push({{name, url}});
    saveMyLinks(links); nameInput.value = ''; urlInput.value = '';
    modal.classList.remove('open'); renderMy();
  }};
  if (modal) modal.onclick = e => {{ if (e.target === modal && cancelBtn) cancelBtn.onclick(); }};

  renderMy(); updatePinDots();
}})();
</script>
</body>
</html>"""
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=".")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    print(f"[WaveDesk] {DATE_STR} {TIME_STR} 크롤링 시작")
    indices, kdci_routes, kcci_routes, ncfi_routes = get_indices()
    news = get_news()

    idx_cnt = sum(1 for v in indices.values() if v["value"] != "—")
    print(f"  지수: {idx_cnt}개 수집")
    for k, v in indices.items():
        print(f"    {k}: {v['value']} {v.get('change','')} ({v.get('date','')})")
    print(f"  세부노선: KDCI {len(kdci_routes)}개 / KCCI {len(kcci_routes)}개 / NCFI {len(ncfi_routes)}개")
    ko_cnt = sum(1 for n in news if n["source"] == "구글뉴스")
    en_cnt = sum(1 for n in news if n["source"] == "해외뉴스")
    print(f"  뉴스: 국내 {ko_cnt}건 / 해외 {en_cnt}건")

    html = build_html(indices, kdci_routes, kcci_routes, ncfi_routes, news)
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
