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
        "BDI":  {"value": "—", "change": "", "label": "발틱운임지수",
                 "date": "", "url": "https://www.shippingnewsnet.com/sdata/page.html?term=1",
                 "note": "매일 · 쉬핑뉴스넷"},
        "KCCI": {"value": "—", "change": "", "label": "한국컨운임지수",
                 "date": "", "url": "https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000",
                 "note": "매주 월 14:00 · 한국해양진흥공사"},
        "BDTI": {"value": "—", "change": "", "label": "발틱탱커지수(원유)",
                 "date": "", "url": "https://www.spotmarketcap.com/shipping",
                 "note": "비정기 갱신 · spotmarketcap.com"},
        "BCTI": {"value": "—", "change": "", "label": "발틱탱커지수(석유제품)",
                 "date": "", "url": "https://www.spotmarketcap.com/shipping",
                 "note": "비정기 갱신 · spotmarketcap.com"},
    }
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

    # KCCI — 한국해양진흥공사 메인
    try:
        r = requests.get("https://www.kobc.or.kr/ebz/shippinginfo/main.do",
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

    # BDTI / BCTI — spotmarketcap.com
    try:
        r = requests.get("https://www.spotmarketcap.com/shipping",
                         headers=HEADERS, timeout=TIMEOUT)
        text = r.text
        m_bdti = re.search(r"BDTI[^\d]{0,5}([\d,]+)[^\d]{0,10}([+\-][\d.]+%)", text)
        m_bcti = re.search(r"BCTI[^\d]{0,5}([\d,]+)[^\d]{0,10}([+\-][\d.]+%)", text)
        if m_bdti:
            base["BDTI"].update({"value": m_bdti.group(1), "change": m_bdti.group(2),
                                  "date": NOW.strftime("%Y-%m-%d")})
        if m_bcti:
            base["BCTI"].update({"value": m_bcti.group(1), "change": m_bcti.group(2),
                                  "date": NOW.strftime("%Y-%m-%d")})
    except Exception as e:
        print(f"  [BDTI/BCTI 오류] {e}")

    return base


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
        for item in root.findall(".//item")[:max_items * 2]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            src_el = item.find("source")
            lbl = src_el.text.strip() if src_el is not None else label
            # 날짜 필터: 오늘/어제 기사만
            if pub:
                try:
                    pub_dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc).astimezone(KST)
                    if pub_dt.date() not in (today, yesterday):
                        continue
                except Exception:
                    pass  # 날짜 파싱 실패 시 포함 (필터 누락 방지)
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
    # 해외 — Google 뉴스 영어 RSS, 다양한 키워드로 여러 매체 자연 혼합 (총 10건, 오늘/어제만)
    en_queries = [
        ("shipping freight rates", 4),
        ("container shipping market", 3),
        ("bulk carrier tanker shipping", 2),
        ("maritime industry news", 3),
    ]
    for q, cnt in en_queries:
        got = fetch_google_news(q.replace(" ","+"), "en", "해외뉴스", "Shipping News", cnt)
        news += got

    # 국내 — Google 뉴스 한국어 RSS (총 10건, 오늘/어제만)
    ko_queries = [
        ("해운+운임", 5),
        ("해운+물류+컨테이너", 3),
        ("벌크선+탱커+해운", 2),
    ]
    for q, cnt in ko_queries:
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


def build_html(indices, news):
    # 지수 카드
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
.header{{display:flex;align-items:baseline;gap:8px;
         margin-bottom:1rem;padding-bottom:.6rem;border-bottom:2px solid #2563eb}}
.brand-name{{font-size:1.15rem;font-weight:700;color:#1e3a8a;letter-spacing:-.5px}}
.brand-sub{{font-size:.75rem;color:#6b7280}}

.sec-label{{font-size:.75rem;font-weight:600;text-transform:uppercase;
            letter-spacing:.8px;color:#6b7280;margin-bottom:.5rem}}

/* 지수 */
.idx-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:.75rem}}
.idx-card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
           padding:1rem 1.25rem;text-decoration:none;color:inherit;
           transition:border-color .15s;display:block}}
.idx-card:hover{{border-color:#2563eb}}
.idx-card.idx-unavail{{opacity:.45}}
.idx-label{{font-size:.72rem;color:#9ca3af;margin-bottom:1px}}
.idx-key{{font-size:.72rem;font-weight:700;color:#6b7280;margin-bottom:.3rem}}
.idx-val{{font-size:1.7rem;font-weight:700;color:#111827}}
.idx-chg{{font-size:.82rem;margin-top:.3rem}}
.idx-date{{font-size:.7rem;color:#9ca3af;margin-top:.2rem}}
.idx-note{{font-size:.68rem;color:#d1d5db;margin-top:.1rem}}
.up{{color:#dc2626}}.dn{{color:#2563eb}}.neu{{color:#9ca3af}}

/* 지수 바로가기 배너 */
.idx-links{{display:flex;gap:8px;margin-bottom:2rem;flex-wrap:wrap}}
.idx-link-btn{{font-size:.75rem;font-weight:500;padding:5px 12px;border-radius:6px;
               text-decoration:none;border:1px solid #e5e7eb;background:#fff;
               color:#374151;transition:border-color .15s,background .15s}}
.idx-link-btn:hover{{border-color:#2563eb;background:#f0f5ff;color:#1e3a8a}}

/* 뉴스 */
.news-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:2rem}}
.news-col{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}}
.news-col-header{{display:flex;align-items:center;gap:8px;padding:.75rem 1rem;
                  background:#f8faff;border-bottom:1px solid #e5e7eb;
                  font-size:.82rem;font-weight:600;color:#1e3a8a}}
.news-inner{{display:flex;flex-direction:column;max-height:330px;overflow-y:auto}}
.src-mini-header{{display:flex;align-items:center;gap:6px;
                  padding:.4rem 1rem;background:#f9fafb;border-bottom:1px solid #f3f4f6}}
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

/* 주요 사이트 */
.links-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:1rem}}
.link-card{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;
            padding:.75rem 1rem;text-decoration:none;color:inherit;transition:border-color .15s}}
.link-card:hover{{border-color:#2563eb}}
.link-card .lc-name{{font-size:.82rem;font-weight:600;color:#111827}}
.link-card .lc-sub{{font-size:.72rem;color:#9ca3af;margin-top:2px}}

/* SM 계열사 탭 */
.affiliate-section{{margin-bottom:1.5rem}}
.affiliate-title{{font-size:.75rem;font-weight:600;text-transform:uppercase;
                  letter-spacing:.8px;color:#6b7280;margin-bottom:.6rem}}
.affiliate-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.aff-card{{background:#1e3a8a;border-radius:8px;padding:.65rem .8rem;
           text-decoration:none;transition:background .15s}}
.aff-card:hover{{background:#1a56db}}
.aff-name{{font-size:.78rem;font-weight:600;color:#fff}}
.aff-desc{{font-size:.68rem;color:#93c5fd;margin-top:2px}}

.footer{{font-size:.72rem;color:#d1d5db;text-align:center;
         padding-top:.75rem;border-top:1px solid #e5e7eb}}

/* 사용자 정의 링크 */
.add-link-btn{{display:block;width:100%;margin-bottom:1.5rem;padding:.7rem;
               background:#fff;border:1.5px dashed #cbd5e1;border-radius:8px;
               color:#6b7280;font-size:.82rem;font-weight:600;cursor:pointer;
               transition:border-color .15s,color .15s}}
.add-link-btn:hover{{border-color:#2563eb;color:#2563eb}}
#customLinksGrid:empty{{display:none}}
#customLinksGrid{{margin-bottom:.75rem}}
.custom-link-card{{position:relative}}
.custom-remove-btn{{position:absolute;top:4px;right:4px;width:18px;height:18px;
                    border-radius:50%;background:#f3f4f6;color:#9ca3af;
                    border:none;font-size:.7rem;cursor:pointer;line-height:18px;
                    text-align:center;padding:0}}
.custom-remove-btn:hover{{background:#fee2e2;color:#dc2626}}

.modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);
                z-index:100;align-items:center;justify-content:center}}
.modal-overlay.open{{display:flex}}
.modal-box{{background:#fff;border-radius:12px;padding:1.5rem;width:320px;max-width:90vw}}
.modal-title{{font-size:.95rem;font-weight:700;color:#111827;margin-bottom:1rem}}
.modal-input{{width:100%;padding:.6rem .8rem;border:1px solid #e5e7eb;border-radius:6px;
              font-size:.85rem;margin-bottom:.6rem;font-family:inherit}}
.modal-input:focus{{outline:none;border-color:#2563eb}}
.modal-btns{{display:flex;gap:8px;margin-top:.5rem}}
.modal-btn{{flex:1;padding:.55rem;border-radius:6px;border:none;
            font-size:.82rem;font-weight:600;cursor:pointer}}
.modal-btn-cancel{{background:#f3f4f6;color:#6b7280}}
.modal-btn-save{{background:#2563eb;color:#fff}}

@media(max-width:700px){{
  .idx-grid{{grid-template-columns:1fr}}
  .news-grid{{grid-template-columns:1fr}}
  .links-grid{{grid-template-columns:repeat(2,1fr)}}
  .affiliate-grid{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <span class="brand-name">⚓ WaveDesk</span>
    <span class="brand-sub">해운 아침 브리핑</span>
  </div>

  <div class="sec-label">📊 해운 시황 지수</div>
  <div class="idx-grid">{idx_html}
  </div>

  <div class="idx-links">
    <a class="idx-link-btn" href="https://surff.kr/indices" target="_blank">📈 SCFI · KCCI · CCFI — surff.kr</a>
    <a class="idx-link-btn" href="https://nlic.go.kr/nlic/ocnStatisticBoard.action" target="_blank">📊 SCFI · CCFI · BDI — 국가물류통합정보센터</a>
    <a class="idx-link-btn" href="https://www.shippingnewsnet.com/sdata/page.html?term=1" target="_blank">📉 BDI · BCI · BPI — 쉬핑뉴스넷</a>
    <a class="idx-link-btn" href="https://www.kobc.or.kr/ebz/shippinginfo/kcci/gridList.do?mId=0304000000" target="_blank">📌 KCCI — 한국해양진흥공사</a>
    <a class="idx-link-btn" href="https://www.balticexchange.com/en/index.html" target="_blank">⚓ Baltic Exchange 공식</a>
    <a class="idx-link-btn" href="https://en.sse.net.cn/indices/scfinew.jsp" target="_blank">🚢 SCFI 공식 — 상하이해운거래소</a>
    <a class="idx-link-btn" href="https://en.sse.net.cn/indices/ccfinew.jsp" target="_blank">🛳️ CCFI 공식 — 상하이해운거래소</a>
    <a class="idx-link-btn" href="https://www.freightos.com/enterprise/terminal/freightos-baltic-index-global-container-pricing-index/" target="_blank">📦 Freightos 글로벌 컨테이너 운임지수 (FBX)</a>
    <a class="idx-link-btn" href="https://www.tradlinx.com/ko/freight-index" target="_blank">📊 TradLinx 운임지수 종합 차트</a>
    <a class="idx-link-btn" href="https://lngprime.com/category/markets/" target="_blank">🔥 LNG 스팟 운임 시황 — LNG Prime</a>
    <a class="idx-link-btn" href="https://www.spotmarketcap.com/shipping" target="_blank">🛢️ 탱커 전 클래스 TCE·Worldscale — spotmarketcap.com</a>
    <a class="idx-link-btn" href="https://www.balticexchange.com/en/data-services/market-information0/indices.html" target="_blank">📋 벌크선 운영비·신조가 지수 — Baltic Exchange</a>
  </div>

  <div class="sec-label">📰 최신 해운 뉴스</div>
  <div class="news-grid">
    {news_html}
  </div>

  <div class="sec-label">⭐ 내가 추가한 사이트 <span style="font-weight:400;color:#9ca3af;text-transform:none;letter-spacing:0">(이 브라우저에만 저장됨)</span></div>
  <div class="links-grid" id="customLinksGrid"></div>
  <button id="addLinkBtn" class="add-link-btn">+ 사이트 추가</button>

  <div id="addLinkModal" class="modal-overlay">
    <div class="modal-box">
      <div class="modal-title">사이트 추가</div>
      <input id="newLinkName" class="modal-input" placeholder="사이트 이름 (예: 내 즐겨찾기)">
      <input id="newLinkUrl" class="modal-input" placeholder="URL (https://... 형식)">
      <div class="modal-btns">
        <button id="cancelLinkBtn" class="modal-btn modal-btn-cancel">취소</button>
        <button id="saveLinkBtn" class="modal-btn modal-btn-save">추가</button>
      </div>
    </div>
  </div>

  <div class="sec-label">🔗 주요 해운 뉴스 사이트</div>
  <div class="links-grid">
    <a class="link-card" href="https://www.ksg.co.kr/news/main_news.jsp" target="_blank">
      <div class="lc-name">코리아쉬핑가제트</div>
      <div class="lc-sub">국내 해운 전문 미디어</div>
    </a>
    <a class="link-card" href="https://www.shippingnewsnet.com/news/articleList.html?sc_sub_section_code=S2N1&view_type=sm" target="_blank">
      <div class="lc-name">쉬핑뉴스넷</div>
      <div class="lc-sub">국내 해운물류 뉴스</div>
    </a>
    <a class="link-card" href="https://www.kobc.or.kr/ebz/shippinginfo/main.do" target="_blank">
      <div class="lc-name">한국해양진흥공사</div>
      <div class="lc-sub">KCCI · 해운시황 보고서</div>
    </a>
    <a class="link-card" href="http://www.maritimepress.co.kr/" target="_blank">
      <div class="lc-name">한국해운신문</div>
      <div class="lc-sub">해운·조선·항만물류 뉴스</div>
    </a>
    <a class="link-card" href="https://www.klnews.co.kr/" target="_blank">
      <div class="lc-name">물류신문</div>
      <div class="lc-sub">물류 전문 매체</div>
    </a>
    <a class="link-card" href="https://maritime-executive.com/" target="_blank">
      <div class="lc-name">Maritime Executive</div>
      <div class="lc-sub">해외 해운 전문 미디어 (영문)</div>
    </a>
  </div>

  <div class="affiliate-section">
    <div class="affiliate-title">🚢 SM그룹 해운 계열사</div>
    <div class="affiliate-grid">
      <a class="aff-card" href="http://www.korealines.co.kr" target="_blank">
        <div class="aff-name">대한해운</div>
        <div class="aff-desc">전용선 · 벌크 · 탱커</div>
      </a>
      <a class="aff-card" href="https://www.smlines.com/kr/" target="_blank">
        <div class="aff-name">SM상선</div>
        <div class="aff-desc">컨테이너 전문 선사</div>
      </a>
      <a class="aff-card" href="http://www.smksc.co.kr/" target="_blank">
        <div class="aff-name">대한상선</div>
        <div class="aff-desc">벌크 · 종합자원 수송</div>
      </a>
      <a class="aff-card" href="https://klclng.com/" target="_blank">
        <div class="aff-name">대한해운LNG</div>
        <div class="aff-desc">LNG 전문 운송</div>
      </a>
      <a class="aff-card" href="https://www.klcsm.co.kr/" target="_blank">
        <div class="aff-name">KLCSM</div>
        <div class="aff-desc">선박관리 · 수리</div>
      </a>
      <a class="aff-card" href="http://www.cmship.co.kr/" target="_blank">
        <div class="aff-name">창명해운</div>
        <div class="aff-desc">벌크 · 특수화물</div>
      </a>
      <a class="aff-card" href="http://www.smlgi.co.kr/index" target="_blank">
        <div class="aff-name">SM상선 경인터미널</div>
        <div class="aff-desc">항만 · 물류 서비스</div>
      </a>
      <a class="aff-card" href="http://www.smlgp.co.kr/index" target="_blank">
        <div class="aff-name">SM상선 김포터미널</div>
        <div class="aff-desc">항만 · 내륙물류</div>
      </a>
      <a class="aff-card" href="https://www.smgroup.co.kr/business/shipping-industry.do" target="_blank">
        <div class="aff-name">SM그룹 (해운부문)</div>
        <div class="aff-desc">그룹 공식 홈페이지</div>
      </a>
    </div>
  </div>

  <div class="footer">
    {DATE_STR} · 업데이트 {TIME_STR} KST<br>
    WaveDesk · 매일 08:00 자동 업데이트 · GitHub Pages 호스팅<br>
    BDI 출처: 쉬핑뉴스넷 · KCCI 출처: 한국해양진흥공사 · 해외 뉴스 제목 Google 번역
  </div>

</div>

<script>
(function() {{
  const STORAGE_KEY = 'wavedesk_custom_links';
  const grid = document.getElementById('customLinksGrid');
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
  function saveLinks(links) {{
    localStorage.setItem(STORAGE_KEY, JSON.stringify(links));
  }}
  function render() {{
    const links = getLinks();
    grid.innerHTML = '';
    links.forEach((l, i) => {{
      const a = document.createElement('a');
      a.className = 'link-card custom-link-card';
      a.href = l.url; a.target = '_blank';
      a.innerHTML = `<div class="lc-name">${{l.name}}</div><div class="lc-sub">사용자 추가</div>`;
      const btn = document.createElement('button');
      btn.className = 'custom-remove-btn';
      btn.textContent = '×';
      btn.onclick = (e) => {{
        e.preventDefault(); e.stopPropagation();
        const updated = getLinks(); updated.splice(i, 1); saveLinks(updated); render();
      }};
      a.appendChild(btn);
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
    const links = getLinks();
    links.push({{name, url}});
    saveLinks(links);
    nameInput.value = ''; urlInput.value = '';
    modal.classList.remove('open');
    render();
  }};
  modal.onclick = (e) => {{ if (e.target === modal) cancelBtn.onclick(); }};
  render();
}})();
</script>
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
        print(f"    {k}: {v['value']} {v.get('change','')} ({v.get('date','')})")
    ko_cnt = sum(1 for n in news if n["source"] == "구글뉴스")
    en_cnt = sum(1 for n in news if n["source"] == "해외뉴스")
    print(f"  뉴스: 국내 {ko_cnt}건 / 해외 {en_cnt}건")

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
