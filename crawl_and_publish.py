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
        "VLSFO": {"value": "—", "change": "", "label": "벙커유(싱가포르)",
                  "date": "", "url": "https://shipandbunker.com/prices/apac/sea/sg-sin-singapore",
                  "note": "매일 · Ship&Bunker ($/MT)"},
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
                if len(l) > i:
                    kdci_routes.append({"route": name, "value": l[i]})
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
            if len(cols) >= 6:
                code, route, cur, prev, wk = cols[1], cols[2], cols[4], cols[5], cols[6] if len(cols) > 6 else ""
                if code == "KCCI":
                    chg = ""
                    m = re.search(r"([+\-]?\d+)\(([+\-][\d.]+%)\)", wk)
                    if m:
                        chg = m.group(2)
                    base["KCCI"].update({"value": cur, "change": chg, "date": NOW.strftime("%Y-%m-%d")})
                elif code and re.match(r"^[A-Z]{3,5}$", code) and cur:
                    kcci_routes.append({"route": f"{route} ({code})", "value": cur})
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
                    ncfi_routes.append({"route": route, "value": cur})
    except Exception as e:
        print(f"  [NCFI 오류] {e}")

    # VLSFO — Ship & Bunker (싱가포르)
    try:
        r = requests.get("https://shipandbunker.com/prices/apac/sea/sg-sin-singapore",
                         headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "lxml")
        # 가격 테이블에서 VLSFO 행 파싱
        for row in soup.select("table tr"):
            cols = [td.get_text(strip=True) for td in row.select("td")]
            if len(cols) >= 3 and "VLSFO" in cols[0]:
                val = cols[1].replace("$","").replace(",","").strip()
                chg = cols[2].strip()
                if re.match(r"[\d.]+", val):
                    base["VLSFO"].update({
                        "value": f"${val}",
                        "change": chg,
                        "date": NOW.strftime("%Y-%m-%d")
                    })
                break
        # fallback: 페이지 텍스트에서 수치 추출
        if base["VLSFO"]["value"] == "—":
            m = re.search(r"VLSFO[^\d]{0,10}(\d{3,4}(?:\.\d+)?)", r.text)
            if m:
                base["VLSFO"].update({"value": f"${m.group(1)}", "date": NOW.strftime("%Y-%m-%d")})
    except Exception as e:
        print(f"  [VLSFO 오류] {e}")

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
      background:#0f1117;color:#e2e8f0;min-height:100vh;font-size:14px}}
.wrap{{max-width:1200px;margin:0 auto;padding:1rem 1.25rem}}

/* ── 헤더 ── */
.header{{display:flex;justify-content:space-between;align-items:center;
         padding:.6rem 0;margin-bottom:1rem;
         border-bottom:1px solid #1e2535}}
.brand{{display:flex;align-items:center;gap:8px}}
.brand-name{{font-size:1rem;font-weight:700;color:#60a5fa;letter-spacing:.5px}}
.brand-sub{{font-size:.72rem;color:#475569;letter-spacing:.3px}}
.header-time{{font-size:.72rem;color:#475569;text-align:right;line-height:1.7}}

/* ── 섹션 라벨 ── */
.sec-label{{font-size:.68rem;font-weight:600;text-transform:uppercase;
            letter-spacing:1px;color:#475569;margin-bottom:.5rem;
            display:flex;align-items:center;gap:6px}}
.sec-label::after{{content:'';flex:1;height:1px;background:#1e2535}}

/* ── 지수 카드 (3열) ── */
.idx-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:.6rem}}
.idx-card{{background:#161b27;border:1px solid #1e2535;border-radius:8px;
           padding:.9rem 1.1rem;text-decoration:none;color:inherit;
           transition:border-color .15s,background .15s;display:block}}
.idx-card:hover{{border-color:#3b82f6;background:#1a2035}}
.idx-card.idx-unavail{{opacity:.4}}
.idx-label{{font-size:.68rem;color:#64748b;letter-spacing:.3px;margin-bottom:2px}}
.idx-key{{font-size:.7rem;font-weight:700;color:#94a3b8;letter-spacing:1px;margin-bottom:.4rem}}
.idx-val{{font-size:1.6rem;font-weight:700;color:#f1f5f9;letter-spacing:-.5px;line-height:1}}
.idx-chg{{font-size:.78rem;margin-top:.35rem;font-weight:500}}
.idx-date{{font-size:.65rem;color:#334155;margin-top:.25rem}}
.idx-note{{font-size:.62rem;color:#1e2535;margin-top:.1rem}}
.up{{color:#f87171}}.dn{{color:#60a5fa}}.neu{{color:#475569}}

/* ── 아코디언 (3열 드롭다운) ── */
.acc-wrap{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:.75rem}}
.accordion{{background:#161b27;border:1px solid #1e2535;border-radius:8px;overflow:hidden}}
.acc-header{{display:flex;justify-content:space-between;align-items:center;
             padding:.5rem .75rem;border-bottom:1px solid #1e2535}}
.acc-toggle{{background:none;border:none;cursor:pointer;font-size:.75rem;
             font-weight:600;color:#94a3b8;font-family:inherit;padding:0;text-align:left}}
.acc-toggle:hover{{color:#60a5fa}}
.acc-arrow{{transition:transform .2s;color:#475569;font-size:.7rem;margin-left:3px}}
.acc-toggle.open .acc-arrow{{transform:rotate(180deg)}}
.acc-link-btn{{font-size:.68rem;padding:2px 7px;border:1px solid #3b82f6;
               border-radius:4px;color:#3b82f6;text-decoration:none;white-space:nowrap}}
.acc-link-btn:hover{{background:#3b82f6;color:#fff}}
.acc-body{{max-height:0;overflow:hidden;transition:max-height .25s ease}}
.acc-body.open{{max-height:220px;overflow-y:auto}}
.acc-rows{{display:flex;flex-direction:column}}
.acc-row{{display:flex;justify-content:space-between;align-items:center;
          padding:.3rem .75rem;border-bottom:1px solid #1a2035}}
.acc-row:last-child{{border-bottom:none}}
.acc-route{{font-size:.7rem;color:#64748b}}
.acc-val{{font-size:.72rem;font-weight:600;color:#e2e8f0}}
.acc-chg{{font-size:.68rem;font-weight:500;margin-left:5px}}
.acc-chg.up{{color:#f87171}}.acc-chg.dn{{color:#60a5fa}}.acc-chg.neu{{color:#475569}}

/* ── 지수 탭 (운임지수 / 연료·환경 / 통계) ── */
.idx-tab-bar{{display:flex;gap:4px;margin-bottom:6px}}
.idx-tab{{padding:4px 12px;border-radius:5px;border:1px solid #1e2535;
          background:transparent;font-size:.72rem;font-weight:600;
          color:#475569;cursor:pointer;font-family:inherit;transition:all .15s}}
.idx-tab.active{{background:#1e40af;color:#fff;border-color:#1e40af}}
.idx-tab:hover:not(.active){{border-color:#3b82f6;color:#60a5fa}}
.idx-tab-panel{{display:none;flex-wrap:wrap;gap:6px;margin-bottom:1rem}}
.idx-tab-panel.active{{display:flex}}
.idx-link-btn{{font-size:.7rem;padding:4px 10px;border-radius:5px;
               border:1px solid #1e2535;background:#161b27;color:#94a3b8;
               text-decoration:none;transition:all .15s;white-space:nowrap}}
.idx-link-btn:hover{{border-color:#3b82f6;color:#60a5fa;background:#1a2035}}

/* ── 뉴스 ── */
.news-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:1rem}}
.news-col{{background:#161b27;border:1px solid #1e2535;border-radius:8px;overflow:hidden}}
.news-col-header{{display:flex;align-items:center;gap:6px;padding:.55rem .9rem;
                  border-bottom:1px solid #1e2535;
                  font-size:.72rem;font-weight:600;color:#94a3b8;letter-spacing:.3px}}
.news-inner{{display:flex;flex-direction:column;max-height:310px;overflow-y:auto}}
.src-mini-header{{padding:.3rem .9rem;background:#0f1117;
                  font-size:.65rem;color:#475569;border-bottom:1px solid #1a2035}}
.news-row{{display:flex;align-items:center;justify-content:space-between;
           padding:.45rem .9rem;border-bottom:1px solid #1a2035;
           text-decoration:none;color:inherit;gap:6px;transition:background .12s}}
.news-row:last-child{{border-bottom:none}}
.news-row:hover{{background:#1a2035}}
.news-title{{font-size:.78rem;line-height:1.4;color:#cbd5e1;flex:1}}
.news-src-tag{{font-size:.62rem;font-weight:600;color:#f97316;background:rgba(249,115,22,.1);
               padding:1px 4px;border-radius:3px;margin-right:4px;
               white-space:nowrap;flex-shrink:0}}
.news-arrow{{font-size:.7rem;color:#334155;flex-shrink:0}}

/* ── 사이트 탭 ── */
.sites-section{{margin-bottom:1rem}}
.site-tab-bar{{display:flex;gap:4px;margin-bottom:8px;border-bottom:1px solid #1e2535;padding-bottom:6px}}
.site-tab{{padding:4px 14px;border-radius:5px;border:none;background:transparent;
           font-size:.75rem;font-weight:600;color:#475569;cursor:pointer;
           font-family:inherit;transition:all .15s}}
.site-tab.active{{background:#1e2535;color:#e2e8f0}}
.site-tab:hover:not(.active){{color:#94a3b8}}
.site-panel{{display:none}}
.site-panel.active{{display:block}}

/* 주요 사이트 카드 */
.site-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:.75rem}}
.site-card{{background:#161b27;border:1px solid #1e2535;border-radius:7px;
            padding:.65rem .9rem;text-decoration:none;color:inherit;
            transition:border-color .15s;display:block}}
.site-card:hover{{border-color:#3b82f6}}
.site-card-name{{font-size:.78rem;font-weight:600;color:#cbd5e1}}
.site-card-sub{{font-size:.65rem;color:#475569;margin-top:2px}}
.site-category{{font-size:.65rem;font-weight:600;text-transform:uppercase;
                letter-spacing:.5px;color:#334155;margin:.6rem 0 .3rem}}

/* SM 계열사 */
.aff-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}}
.aff-card{{background:#1e3a8a;border:1px solid #1e40af;border-radius:7px;
           padding:.55rem .8rem;text-decoration:none;transition:background .15s}}
.aff-card:hover{{background:#1d4ed8}}
.aff-name{{font-size:.75rem;font-weight:600;color:#dbeafe}}
.aff-desc{{font-size:.62rem;color:#93c5fd;margin-top:1px}}

/* 내 사이트 탭 */
.my-site-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.my-site-hint{{font-size:.68rem;color:#334155}}
.my-add-btn{{font-size:.72rem;padding:4px 10px;border-radius:5px;
             border:1px solid #1e2535;background:transparent;color:#60a5fa;
             cursor:pointer;font-family:inherit}}
.my-add-btn:hover{{background:#1e2535}}
.my-site-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;min-height:60px}}
.my-site-grid.drag-over{{outline:2px dashed #3b82f6;border-radius:8px}}
.my-card{{background:#161b27;border:1px solid #1e2535;border-radius:7px;
          padding:.65rem .9rem;text-decoration:none;color:inherit;
          position:relative;cursor:grab;transition:border-color .15s,opacity .15s}}
.my-card:hover{{border-color:#3b82f6}}
.my-card.dragging{{opacity:.4;cursor:grabbing}}
.my-card-name{{font-size:.78rem;font-weight:600;color:#cbd5e1}}
.my-card-sub{{font-size:.65rem;color:#475569;margin-top:2px}}
.my-del-btn{{position:absolute;top:4px;right:4px;width:16px;height:16px;
             border-radius:50%;background:#1e2535;color:#475569;border:none;
             font-size:.65rem;cursor:pointer;line-height:16px;text-align:center;padding:0}}
.my-del-btn:hover{{background:#7f1d1d;color:#fca5a5}}
.my-empty{{grid-column:1/-1;text-align:center;padding:1.5rem;
           font-size:.75rem;color:#334155;border:1px dashed #1e2535;border-radius:7px}}

/* 모달 */
.modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);
                z-index:100;align-items:center;justify-content:center}}
.modal-overlay.open{{display:flex}}
.modal-box{{background:#161b27;border:1px solid #1e2535;border-radius:10px;
            padding:1.25rem;width:300px;max-width:90vw}}
.modal-title{{font-size:.88rem;font-weight:700;color:#e2e8f0;margin-bottom:.9rem}}
.modal-input{{width:100%;padding:.5rem .75rem;border:1px solid #1e2535;
              border-radius:6px;font-size:.8rem;margin-bottom:.5rem;
              font-family:inherit;background:#0f1117;color:#e2e8f0}}
.modal-input:focus{{outline:none;border-color:#3b82f6}}
.modal-btns{{display:flex;gap:6px;margin-top:.4rem}}
.modal-btn{{flex:1;padding:.5rem;border-radius:6px;border:none;
            font-size:.78rem;font-weight:600;cursor:pointer}}
.modal-btn-cancel{{background:#1e2535;color:#94a3b8}}
.modal-btn-save{{background:#2563eb;color:#fff}}

.footer{{font-size:.65rem;color:#1e2535;text-align:center;
         padding-top:.75rem;margin-top:.5rem;border-top:1px solid #1e2535}}

@media(max-width:700px){{
  .idx-grid{{grid-template-columns:1fr 1fr}}
  .acc-wrap{{grid-template-columns:1fr}}
  .news-grid{{grid-template-columns:1fr}}
  .site-grid{{grid-template-columns:repeat(2,1fr)}}
  .aff-grid{{grid-template-columns:repeat(2,1fr)}}
  .my-site-grid{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="brand">
      <span class="brand-name">⚓ WAVEDESK</span>
      <span class="brand-sub">해운 아침 브리핑</span>
    </div>
    <div class="header-time">{DATE_STR} &nbsp;·&nbsp; {TIME_STR} KST</div>
  </div>

  <div class="sec-label">해운 시황 지수</div>
  <div class="idx-grid">{idx_html}
  </div>

  <div class="acc-wrap">
    {accordions_html}
  </div>

  <div class="idx-tab-bar">
    <button class="idx-tab active" data-tab="tab-idx">운임지수</button>
    <button class="idx-tab" data-tab="tab-env">연료·환경</button>
    <button class="idx-tab" data-tab="tab-stat">통계·보고서</button>
  </div>
  <div class="idx-tab-panel active" id="tab-idx">
    <a class="idx-link-btn" href="https://surff.kr/indices" target="_blank">SCFI·KCCI·CCFI — surff.kr</a>
    <a class="idx-link-btn" href="https://nlic.go.kr/nlic/ocnStatisticBoard.action" target="_blank">SCFI·CCFI·BDI — 국가물류통합정보센터</a>
    <a class="idx-link-btn" href="https://www.shippingnewsnet.com/sdata/page.html?term=1" target="_blank">BDI·BCI·BPI — 쉬핑뉴스넷</a>
    <a class="idx-link-btn" href="https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000" target="_blank">KCCI — 한국해양진흥공사</a>
    <a class="idx-link-btn" href="https://www.balticexchange.com/en/index.html" target="_blank">Baltic Exchange</a>
    <a class="idx-link-btn" href="https://en.sse.net.cn/indices/scfinew.jsp" target="_blank">SCFI — 상하이해운거래소</a>
    <a class="idx-link-btn" href="https://en.sse.net.cn/indices/ccfinew.jsp" target="_blank">CCFI — 상하이해운거래소</a>
    <a class="idx-link-btn" href="https://www.freightos.com/enterprise/terminal/freightos-baltic-index-global-container-pricing-index/" target="_blank">Freightos FBX</a>
    <a class="idx-link-btn" href="https://www.tradlinx.com/ko/freight-index" target="_blank">TradLinx 종합 차트</a>
    <a class="idx-link-btn" href="https://www.spotmarketcap.com/shipping" target="_blank">탱커 TCE·Worldscale</a>
  </div>
  <div class="idx-tab-panel" id="tab-env">
    <a class="idx-link-btn" href="https://shipandbunker.com/prices" target="_blank">⛽ 글로벌 벙커유 — Ship&Bunker</a>
    <a class="idx-link-btn" href="https://shipandbunker.com/prices/ea/eu/eu-eua" target="_blank">💶 EU-ETS 탄소배출권</a>
    <a class="idx-link-btn" href="https://lngprime.com/" target="_blank">🔥 LNG 스팟 — LNG Prime</a>
    <a class="idx-link-btn" href="https://kr.investing.com/commodities/carbon-emissions-historical-data" target="_blank">📉 EUA 과거 가격</a>
    <a class="idx-link-btn" href="https://kr.investing.com/commodities/lng-japan-korea-marker-platts-futures" target="_blank">🌊 JKM LNG 스팟</a>
    <a class="idx-link-btn" href="https://www.balticexchange.com/en/data-services/market-information0/indices.html" target="_blank">📋 벌크선 운영비·신조가</a>
  </div>
  <div class="idx-tab-panel" id="tab-stat">
    <a class="idx-link-btn" href="https://nlic.go.kr/nlic/seaStatisticBoard.action" target="_blank">🚢 해상 운송 통계</a>
    <a class="idx-link-btn" href="https://www.kobc.or.kr/ebz/shippinginfo/reportDaily/list.do?mId=0201000000" target="_blank">📄 KOBC 일간 건화물선 보고서</a>
    <a class="idx-link-btn" href="https://www.kobc.or.kr/ebz/shippinginfo/reportWeekly/view.do?mId=0202000000" target="_blank">📄 KOBC 주간통합 보고서</a>
    <a class="idx-link-btn" href="https://www.kobc.or.kr/ebz/shippinginfo/kdci/gridList.do?mId=0301000000" target="_blank">📊 KDCI 세부지수</a>
    <a class="idx-link-btn" href="https://www.kobc.or.kr/ebz/shippinginfo/ncfi/gridList.do?mId=0305000000" target="_blank">📊 NCFI 닝보 노선별</a>
  </div>

  <div class="sec-label">최신 해운 뉴스</div>
  <div class="news-grid">
    {news_html}
  </div>

  <div class="sites-section">
    <div class="sec-label">사이트</div>
    <div class="site-tab-bar">
      <button class="site-tab active" data-stab="stab-my">내 사이트</button>
      <button class="site-tab" data-stab="stab-main">주요 사이트</button>
      <button class="site-tab" data-stab="stab-aff">SM그룹 계열사</button>
    </div>

    <div class="site-panel active" id="stab-my">
      <div class="my-site-header">
        <span class="my-site-hint">드래그로 순서 변경 · 내 브라우저에만 저장</span>
        <button class="my-add-btn" id="addLinkBtn">+ 사이트 추가</button>
      </div>
      <div class="my-site-grid" id="mySiteGrid">
        <div class="my-empty" id="myEmpty">사이트를 추가해보세요</div>
      </div>
    </div>

    <div class="site-panel" id="stab-main">
      <div class="site-category">뉴스 · 미디어</div>
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
      </div>
      <div class="site-category">기관 · 데이터</div>
      <div class="site-grid">
        <a class="site-card" href="https://www.kobc.or.kr/ebz/shippinginfo/main.do" target="_blank">
          <div class="site-card-name">한국해양진흥공사</div><div class="site-card-sub">KCCI · 해운시황 보고서</div></a>
        <a class="site-card" href="https://www.nlic.go.kr/nlic/transInPortCt.action" target="_blank">
          <div class="site-card-name">국가물류통합정보센터</div><div class="site-card-sub">SCFI · CCFI · BDI</div></a>
        <a class="site-card" href="https://surff.kr/indices" target="_blank">
          <div class="site-card-name">surff.kr</div><div class="site-card-sub">운임지수 차트</div></a>
        <a class="site-card" href="https://shipandbunker.com/prices" target="_blank">
          <div class="site-card-name">Ship&Bunker</div><div class="site-card-sub">글로벌 벙커유 가격</div></a>
      </div>
    </div>

    <div class="site-panel" id="stab-aff">
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
  // ── 지수 탭
  document.querySelectorAll('.idx-tab').forEach(t => {{
    t.addEventListener('click', () => {{
      document.querySelectorAll('.idx-tab').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.idx-tab-panel').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      document.getElementById(t.dataset.tab).classList.add('active');
    }});
  }});

  // ── 아코디언
  document.querySelectorAll('.acc-toggle').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const body = document.getElementById(btn.dataset.target);
      const isOpen = body.classList.toggle('open');
      btn.classList.toggle('open', isOpen);
    }});
  }});

  // ── 사이트 탭
  document.querySelectorAll('.site-tab').forEach(t => {{
    t.addEventListener('click', () => {{
      document.querySelectorAll('.site-tab').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.site-panel').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      document.getElementById(t.dataset.stab).classList.add('active');
    }});
  }});

  // ── 내 사이트 (localStorage + drag & drop)
  const STORAGE_KEY = 'wavedesk_my_sites_v2';
  const grid = document.getElementById('mySiteGrid');
  const empty = document.getElementById('myEmpty');
  const modal = document.getElementById('addLinkModal');
  const addBtn = document.getElementById('addLinkBtn');
  const cancelBtn = document.getElementById('cancelLinkBtn');
  const saveBtn = document.getElementById('saveLinkBtn');
  const nameInput = document.getElementById('newLinkName');
  const urlInput = document.getElementById('newLinkUrl');

  function getLinks() {{
    try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }}
    catch(e) {{ return []; }}
  }}
  function saveLinks(links) {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(links)); }}

  let dragSrc = null;

  function render() {{
    const links = getLinks();
    const cards = grid.querySelectorAll('.my-card');
    cards.forEach(c => c.remove());
    empty.style.display = links.length ? 'none' : 'block';
    links.forEach((l, i) => {{
      const a = document.createElement('a');
      a.className = 'my-card';
      a.href = l.url; a.target = '_blank';
      a.draggable = true;
      a.dataset.idx = i;
      a.innerHTML = `<div class="my-card-name">${{l.name}}</div>
        <div class="my-card-sub">내 사이트</div>
        <button class="my-del-btn" title="삭제">×</button>`;
      a.querySelector('.my-del-btn').onclick = (e) => {{
        e.preventDefault(); e.stopPropagation();
        const updated = getLinks(); updated.splice(i, 1); saveLinks(updated); render();
      }};
      a.addEventListener('dragstart', e => {{
        dragSrc = i; a.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      }});
      a.addEventListener('dragend', () => a.classList.remove('dragging'));
      a.addEventListener('dragover', e => {{ e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }});
      a.addEventListener('drop', e => {{
        e.preventDefault();
        if (dragSrc === null || dragSrc === i) return;
        const updated = getLinks();
        const [moved] = updated.splice(dragSrc, 1);
        updated.splice(i, 0, moved);
        saveLinks(updated); dragSrc = null; render();
      }});
      grid.appendChild(a);
    }});
  }}

  addBtn.onclick = () => {{ modal.classList.add('open'); nameInput.focus(); }};
  cancelBtn.onclick = () => {{
    modal.classList.remove('open'); nameInput.value = ''; urlInput.value = '';
  }};
  saveBtn.onclick = () => {{
    let name = nameInput.value.trim();
    let url = urlInput.value.trim();
    if (!url) return;
    if (!/^https?:\\/\\//.test(url)) url = 'https://' + url;
    if (!name) name = url.replace(/^https?:\\/\\//, '').split('/')[0];
    const links = getLinks(); links.push({{name, url}});
    saveLinks(links); nameInput.value = ''; urlInput.value = '';
    modal.classList.remove('open'); render();
  }};
  modal.onclick = e => {{ if (e.target === modal) cancelBtn.onclick(); }};
  render();
}})();
</script>
</body>
</html>"""
