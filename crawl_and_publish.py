"""
WaveDesk - 해운 아침 브리핑
"""
import os, subprocess, sys, re, xml.etree.ElementTree as ET, json
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

# 오늘의 해운 단어 (날짜 기반 고정 선택 — 매일 같은 단어, words.json 순환)
def get_word_of_day():
    try:
        words_path = Path(__file__).parent / "words.json"
        words = json.loads(words_path.read_text(encoding="utf-8"))
        day_index = NOW.timetuple().tm_yday % len(words)  # 1년 365일 순환
        return words[day_index]
    except Exception:
        return None

WORD_OF_DAY = get_word_of_day()

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

    # USD/KRW 환율 — 한국수출입은행 API (매매기준율, deal_bas_r)
    krw_val, krw_chg = None, ""
    cache_path = Path(__file__).parent / "rate_cache.json"
    exim_key = os.environ.get("KOREAEXIM_API_KEY", "")

    if exim_key:
        try:
            today_str = NOW.strftime("%Y%m%d")
            url = f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={exim_key}&searchdate={today_str}&data=AP01"
            r = requests.get(url, headers=HEADERS, timeout=8)
            data = r.json()
            today_krw = None
            for item in data:
                if item.get("cur_unit") == "USD":
                    val = item.get("deal_bas_r", "").replace(",", "")
                    if val:
                        today_krw = float(val)
                    break
            if not today_krw:
                raise ValueError("USD 데이터 없음")
            krw_val = str(round(today_krw))

            # 전일비: cache에서 어제 환율과 비교
            try:
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
                prev_date = cache.get("date", "")
                prev_krw  = float(cache.get("krw", today_krw))
                saved_chg = cache.get("chg", "")
                today_date = NOW.strftime("%Y-%m-%d")
                if prev_date == today_date:
                    krw_chg = saved_chg  # 당일 재실행 시 저장값 재사용
                elif prev_krw and prev_date != today_date:
                    diff = today_krw - prev_krw
                    pct  = round(diff / prev_krw * 100, 2)
                    krw_chg = f"+{pct}%" if pct >= 0 else f"{pct}%"
            except Exception as ce:
                print(f"  [환율 캐시 읽기 오류] {ce}")

            # 캐시 저장
            cache_path.write_text(
                json.dumps({"date": NOW.strftime("%Y-%m-%d"),
                            "krw": today_krw, "chg": krw_chg},
                           ensure_ascii=False), encoding="utf-8")
            print(f"  [환율] 수출입은행: {krw_val} ({krw_chg})")

        except Exception as e:
            print(f"  [환율 수출입은행 오류] {e}")
            # fallback: open.er-api
            try:
                r2 = requests.get("https://open.er-api.com/v6/latest/USD",
                                  headers=HEADERS, timeout=8)
                fb = float(r2.json().get("rates", {}).get("KRW", 0))
                if fb and 900 < fb < 2000:
                    krw_val = str(round(fb))
            except Exception:
                pass
    else:
        print("  [환율] API 키 없음 — open.er-api fallback")
        try:
            r2 = requests.get("https://open.er-api.com/v6/latest/USD",
                              headers=HEADERS, timeout=8)
            fb = float(r2.json().get("rates", {}).get("KRW", 0))
            if fb and 900 < fb < 2000:
                krw_val = str(round(fb))
                # 캐시 기반 전일비
                try:
                    cache = json.loads(cache_path.read_text(encoding="utf-8"))
                    prev_krw = float(cache.get("krw", fb))
                    prev_date = cache.get("date", "")
                    today_date = NOW.strftime("%Y-%m-%d")
                    if prev_date == today_date:
                        krw_chg = cache.get("chg", "")
                    elif prev_krw:
                        diff = fb - prev_krw
                        pct = round(diff / prev_krw * 100, 2)
                        krw_chg = f"+{pct}%" if pct >= 0 else f"{pct}%"
                    cache_path.write_text(
                        json.dumps({"date": today_date, "krw": fb, "chg": krw_chg},
                                   ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
        except Exception as e2:
            print(f"  [환율 fallback 오류] {e2}")

    base["USD/KRW"] = {
        "value":  f"{int(krw_val):,}" if krw_val else "—",
        "change": krw_chg,
        "label":  "원달러환율",
        "date":   NOW.strftime("%Y-%m-%d"),
        "url":    "https://finance.naver.com/marketindex/",
        "note":   "매일 · 수출입은행(매매기준율)"
    }
    print(f"  [환율 최종] {base['USD/KRW']['value']} {base['USD/KRW']['change']}")

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
        cutoff = NOW.replace(hour=0, minute=0, second=0) - timedelta(hours=48)  # 2일 전 자정
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
    """국내/해외 각 10~15개, 해운 우선 정렬"""
    # 해운 핵심 키워드 (우선순위 높음)
    SHIPPING_KW = [
        "컨테이너", "벌크", "탱커", "해운", "운임", "선박", "선사",
        "VLCC", "Capesize", "freight", "shipping", "vessel", "tanker",
        "bulk", "container", "LNG carrier", "charter"
    ]

    def is_shipping(title):
        t = title.lower()
        return any(k.lower() in t for k in SHIPPING_KW)

    # 해외 — 15개 목표
    en_queries = [
        ("shipping+freight+rates", 3),
        ("container+shipping+market", 3),
        ("bulk+carrier+shipping", 3),
        ("tanker+freight+rate", 2),
        ("maritime+industry+news", 2),
        ("LNG+carrier+charter", 2),
    ]
    en_all = []
    for q, cnt in en_queries:
        en_all += fetch_google_news(q, "en", "해외뉴스", "Shipping News", cnt)

    # 국내 — 해운 우선 + 조선·물류·항만 포함, 12개 목표
    ko_core = [
        ("해운+운임", 4),       # 해운 최우선
        ("컨테이너선+운임", 3),
        ("벌크선+탱커+해운", 3),
        ("해상운임+물동량", 2),
        ("해운+선사", 2),
    ]
    ko_related = [
        ("선박+조선+수주", 2),   # 조선
        ("LNG선+벙커링", 2),
        ("항만+물류+해운", 2),   # 항만·물류(해상 한정)
        ("보세운송+해상물류", 1),
        ("선박관리+해운", 2),
    ]
    ko_all = []
    for q, cnt in ko_core + ko_related:
        ko_all += fetch_google_news(q, "ko", "구글뉴스", "국내뉴스", cnt)

    def extract_nouns(title):
        """한글 2글자 이상 단어 집합 추출 (조사·접사 제외 근사치)"""
        return set(w for w in re.findall(r"[가-힣]{2,}", title))

    def dedup_sort(items):
        seen_prefix = set()
        result = []
        for n in items:
            t = n["title"]
            # 1차: 앞 20자 prefix 동일 → 확실한 중복
            prefix = re.sub(r"[^가-힣a-zA-Z0-9]", "", t)[:20]
            if prefix in seen_prefix:
                continue
            # 2차: 기존 기사들과 한글 명사 4개 이상 겹치면 유사 기사로 판단
            nouns = extract_nouns(t)
            is_dup = False
            for existing in result:
                overlap = nouns & extract_nouns(existing["title"])
                if len(overlap) >= 3:
                    is_dup = True
                    break
            if not is_dup:
                seen_prefix.add(prefix)
                result.append(n)
        result.sort(key=lambda x: 0 if is_shipping(x["title"]) else 1)
        return result

    ko_news = dedup_sort(ko_all)[:12]
    en_news = dedup_sort(en_all)[:12]

    result = ko_news + en_news
    result = translate_titles(result)
    return result


# SM그룹 전체 계열사 (smgroup.co.kr 확인 기준)
SM_SHIPPING = [
    "대한해운", "SM상선", "대한상선", "대한해운LNG", "대한해운엘엔지",
    "KLCSM", "창명해운", "SM상선경인터미널", "SM상선김포터미널",
    "한국선박금융",
]
SM_ALL_COMPANIES = SM_SHIPPING + [
    # 제조
    "남선알미늄", "티케이케미칼", "SM벡셀", "화진", "SM스틸",
    "SM인더스트리", "SM중공업", "한덕철광산업", "이엔에이치",
    # 건설
    "SM삼환기업", "삼환기업", "우방",
    # 미디어·서비스
    "ubc울산방송", "UBC", "SM하이플러스", "SM신용정보",
    "SM바로코사", "신촌역사",
    # 레저
    "동강시스타",
    # 그룹 공통
    "SM그룹", "에스엠그룹", "우오현",
]

SM_QUERIES = [
    "SM그룹+대한해운",
    "SM그룹+SM상선",
    "SM그룹+KLCSM",
    "대한상선+창명해운",
    "대한해운LNG",
    "SM그룹+해운",
    "SM그룹+계열사",
    "SM그룹+우오현",
    "SM그룹+남선알미늄",
    "SM그룹+SM벡셀",
]

def get_sm_news():
    """SM그룹 전체 계열사 뉴스 - 최근 3일치, 매일 갱신, 최소 4개 보장"""

    def sm_nouns(t):
        t = re.sub(r"[-–—]\s*[가-힣a-zA-Z0-9]+$", "", t).strip()
        return set(w for w in re.findall(r"[가-힣]{2,}", t))

    def is_dup(title, existing_list):
        nouns = sm_nouns(title)
        prefix = re.sub(r"[^가-힣a-zA-Z0-9]", "", title)[:15]
        for ex in existing_list:
            if re.sub(r"[^가-힣a-zA-Z0-9]", "", ex["title"])[:15] == prefix:
                return True
            if len(nouns & sm_nouns(ex["title"])) >= 3:
                return True
        return False

    def fetch_sm(cutoff_days, max_per_query=8):
        items = []
        cutoff = NOW - timedelta(days=cutoff_days)
        for q in SM_QUERIES:
            url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
            try:
                r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                root = ET.fromstring(r.content)
                for item in root.findall(".//item")[:max_per_query]:
                    title = (item.findtext("title") or "").strip()
                    link  = (item.findtext("link") or "").strip()
                    pub   = (item.findtext("pubDate") or "").strip()
                    src_el = item.find("source")
                    lbl = src_el.text.strip() if src_el is not None else "뉴스"
                    if pub:
                        try:
                            pub_dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc).astimezone(KST)
                            if pub_dt < cutoff:
                                continue
                        except Exception:
                            pass
                    is_ship = any(c in title for c in SM_SHIPPING)
                    if title and link:
                        items.append({
                            "title": title, "url": link,
                            "label": lbl,
                            "category": "해운" if is_ship else "그룹"
                        })
            except Exception:
                pass
        return items

    # 1차: 3일치
    raw = fetch_sm(3)
    result = []
    for n in raw:
        if not is_dup(n["title"], result):
            result.append(n)

    # 2차: 4개 미달 시 7일로 확장
    if len(result) < 4:
        raw2 = fetch_sm(7, max_per_query=10)
        for n in raw2:
            if len(result) >= 8:
                break
            if not is_dup(n["title"], result):
                result.append(n)

    # 3차: 여전히 4개 미달 시 30일로 확장 (최근 뉴스 가뭄 대비)
    if len(result) < 4:
        raw3 = fetch_sm(30, max_per_query=5)
        for n in raw3:
            if len(result) >= 6:
                break
            if not is_dup(n["title"], result):
                result.append(n)

    result.sort(key=lambda x: 0 if x["category"] == "해운" else 1)
    return result[:8]


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


def build_html(indices, kdci_routes, kcci_routes, ncfi_routes, news, sm_news):
    # 오늘의 단어 박스 HTML
    w = WORD_OF_DAY
    if w:
        word_html = f"""<div class="word-box">
      <div class="word-header">📖 오늘의 해운 단어</div>
      <div class="word-main">
        <span class="word-term">{w['word']}</span>
        <span class="word-pos">{w['pos']}</span>
        <span class="word-meaning">{w['meaning']}</span>
      </div>
      <div class="word-sentence">"{w['sentence']}"</div>
      <div class="word-sentence-ko">{w['sentence_ko']}</div>
    </div>"""
    else:
        word_html = ""

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
        rows = ""
        if not routes:
            rows = '<div class="acc-row"><span class="acc-route" style="color:#9ca3af">데이터 없음 (주간 발표일 확인)</span></div>'
        else:
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

    # 뉴스 국내/해외 분리 (각 최대 15개)
    ko_news = [n for n in news if n["source"] == "구글뉴스"][:15]
    en_news = [n for n in news if n["source"] == "해외뉴스"][:15]

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

    # SM그룹 계열사 뉴스 HTML (항상 표시, 비면 안내 메시지)
    sm_rows = ""
    for n in sm_news:
        badge_cls = "sm-badge-ship" if n["category"] == "해운" else "sm-badge-group"
        badge_txt = "해운" if n["category"] == "해운" else "그룹"
        title = n["title"][:60] + ("…" if len(n["title"]) > 60 else "")
        sm_rows += f"""
          <a class="sm-news-row" href="{n['url']}" target="_blank" rel="noopener noreferrer">
            <span class="sm-badge {badge_cls}">{badge_txt}</span>
            <span class="sm-news-title">{title}</span>
            <span class="sm-news-src">{n['label']}</span>
            <span class="news-arrow">↗</span>
          </a>"""

    sm_news_html = f"""
      <div class="sm-news-box">
        <div class="sm-news-header">
          <span class="sm-news-icon">🚢</span> SM그룹 계열사 소식
          <span class="sm-news-sub">최근 3일 · Google 뉴스</span>
        </div>
        <div class="sm-news-grid" data-count="{len(sm_news)}">
          {sm_rows if sm_rows else '<div class="sm-news-empty">최근 3일 뉴스가 없어요</div>'}
        </div>
      </div>"""

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
<title>KLCSM Desk · 해운 브리핑</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🚢</text></svg>">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans KR',sans-serif;
      background:#f0f4f8;color:#1a1a2e;min-height:100vh}}
.wrap{{max-width:1100px;margin:0 auto;padding:.75rem 1.25rem}}

/* 헤더 */
.header{{display:flex;flex-direction:row;align-items:center;gap:36px;
         margin-bottom:.75rem;padding-bottom:.55rem;border-bottom:2px solid #2563eb}}
.header-left{{display:flex;flex-direction:column;gap:6px;flex-shrink:0;min-width:160px}}
.brand{{display:flex;align-items:baseline;gap:8px;flex-shrink:0;padding-top:3px}}
.brand-name{{font-size:1rem;font-weight:700;color:#1e3a8a;letter-spacing:-.5px}}
.brand-sub{{font-size:.72rem;color:#6b7280}}

/* 날씨+단어 래퍼 - 가로 배치 */
.weather-word-wrap{{display:flex;flex-direction:row;align-items:flex-start;gap:10px;
                    flex:1;min-width:0;margin-left:auto}}
/* 날씨 바 */
.weather-bar{{display:flex;gap:6px;flex-wrap:wrap;align-items:flex-start}}
.weather-chip{{display:flex;flex-direction:column;align-items:center;
              padding:8px 14px;background:#f0f7ff;border:1px solid #dbeafe;
              border-radius:10px;font-size:.72rem;color:#1e3a8a;
              white-space:nowrap;min-width:72px;text-align:center}}
.weather-chip-icon{{font-size:1.4rem;line-height:1}}
.weather-chip-name{{font-size:.68rem;font-weight:600;color:#374151;margin-top:1px}}
.weather-chip-temp{{font-size:.9rem;font-weight:700;color:#2563eb}}
.weather-chip-link{{font-size:.62rem;color:#93c5fd;text-decoration:none;margin-top:1px}}
.weather-chip-link:hover{{color:#2563eb}}
.weather-setting-btn{{background:none;border:none;cursor:pointer;color:#9ca3af;
                       font-size:.75rem;padding:2px 4px;margin-left:2px;
                       vertical-align:middle;line-height:1}}
.weather-setting-btn:hover{{color:#374151}}
/* 날씨 설정 모달 */
.weather-modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:200}}
.weather-modal-overlay.open{{display:flex;align-items:center;justify-content:center}}
.weather-modal{{background:#fff;border-radius:12px;padding:20px;width:320px;
                box-shadow:0 8px 32px rgba(0,0,0,.15)}}
.weather-modal-title{{font-size:.85rem;font-weight:700;color:#1e3a8a;margin-bottom:12px}}
.weather-city-row{{display:flex;gap:6px;align-items:center;margin-bottom:6px}}
.weather-city-row input{{flex:1;font-size:.75rem;padding:4px 8px;border:1px solid #d1d5db;
                          border-radius:6px}}
.weather-city-row span{{font-size:.68rem;color:#9ca3af;white-space:nowrap}}
.weather-modal-btns{{display:flex;gap:6px;margin-top:12px;justify-content:flex-end}}
.weather-modal-btns button{{font-size:.75rem;padding:5px 14px;border-radius:6px;
                             cursor:pointer;border:1px solid #d1d5db}}
.weather-modal-save{{background:#1e3a8a;color:#fff;border-color:#1e3a8a!important}}
.word-box{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
           padding:.5rem 1rem;max-width:420px;min-width:0;margin-left:auto}}
.word-header{{font-size:.62rem;font-weight:600;color:#9ca3af;
              text-transform:uppercase;letter-spacing:.5px;margin-bottom:.15rem}}
.word-main{{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;margin-bottom:.1rem}}
.word-term{{font-size:.88rem;font-weight:700;color:#1e3a8a}}
.word-pos{{font-size:.65rem;color:#9ca3af;font-style:italic}}
.word-meaning{{font-size:.72rem;color:#374151;font-weight:500}}
.word-sentence{{font-size:.7rem;color:#6b7280;font-style:italic;margin-bottom:.05rem}}
.word-sentence-ko{{font-size:.68rem;color:#9ca3af}}

/* 섹션 라벨 */
.sec-label{{font-size:.72rem;font-weight:600;text-transform:uppercase;
            letter-spacing:.8px;color:#6b7280;margin-bottom:.5rem}}

/* 지수 카드 (4열) */
.idx-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:.5rem}}
.idx-card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
           padding:.7rem 1rem;text-decoration:none;color:inherit;
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
.news-inner{{display:flex;flex-direction:column;max-height:200px;overflow-y:auto}}
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

/* SM그룹 계열사 뉴스 박스 */
.sm-news-box{{background:linear-gradient(135deg,#eef2ff 0%,#f0f7ff 100%);
              border:1px solid #c7d2fe;border-radius:10px;
              padding:.75rem 1rem;margin-bottom:.75rem}}
.sm-news-header{{display:flex;align-items:center;gap:6px;font-size:.78rem;
                 font-weight:600;color:#1e3a8a;margin-bottom:.6rem}}
.sm-news-icon{{font-size:.9rem}}
.sm-news-sub{{font-size:.67rem;color:#6b7280;font-weight:400;margin-left:auto}}
.sm-news-grid{{display:grid;grid-template-columns:1fr 1fr;gap:4px;
               max-height:240px;overflow-y:auto}}
.sm-news-grid.cols3{{grid-template-columns:1fr 1fr 1fr}}
.sm-news-row{{display:flex;align-items:center;gap:6px;padding:.38rem .6rem;
              border-radius:6px;background:#fff;border:1px solid #e0e7ff;
              text-decoration:none;color:inherit;transition:border-color .12s;
              font-size:.78rem}}
.sm-news-row:hover{{border-color:#4f46e5;background:#f5f3ff}}
.sm-badge{{font-size:.62rem;font-weight:700;padding:1px 5px;border-radius:3px;
           white-space:nowrap;flex-shrink:0}}
.sm-badge-ship{{background:#1e3a8a;color:#fff}}
.sm-badge-group{{background:#e0e7ff;color:#3730a3}}
.sm-news-title{{font-size:.76rem;color:#111827;flex:1;line-height:1.3}}
.sm-news-src{{font-size:.65rem;color:#9ca3af;white-space:nowrap;flex-shrink:0}}
.sm-news-empty{{grid-column:1/-1;text-align:center;padding:.75rem;
                font-size:.75rem;color:#9ca3af}}
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

/* 접기 패널 */
.collapse-panel{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
                 margin-bottom:.75rem;overflow:hidden}}
.collapse-toggle{{width:100%;display:flex;justify-content:space-between;
                  align-items:center;padding:.6rem .9rem;background:#f8faff;
                  border:none;cursor:pointer;font-size:.78rem;font-weight:600;
                  color:#374151;font-family:inherit;text-align:left}}
.collapse-toggle:hover{{background:#eff6ff;color:#1e3a8a}}
.collapse-arrow{{font-size:.72rem;color:#9ca3af;transition:transform .2s}}
.collapse-toggle.open .collapse-arrow{{transform:rotate(180deg)}}
.collapse-body{{display:none;padding:.6rem .9rem .75rem}}
.collapse-body.open{{display:block}}

/* EUA D-Day 박스 */
.eua-box{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;
          padding:.85rem 1.1rem;margin-bottom:.75rem}}
.eua-title{{font-size:.8rem;font-weight:600;color:#1e3a8a;margin-bottom:.5rem}}
.eua-body{{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:.4rem}}
.eua-item{{display:flex;align-items:center;gap:8px;padding:5px 10px;
           border-radius:7px;background:#f8faff;border:1px solid #e5e7eb}}
.eua-year{{font-size:.7rem;color:#6b7280;font-weight:600;flex-shrink:0}}
.eua-date{{font-size:.72rem;color:#374151;white-space:nowrap;flex-shrink:0}}
.eua-dday{{font-size:.72rem;font-weight:700;padding:2px 7px;border-radius:4px;flex-shrink:0}}
.eua-dday.near{{background:#fee2e2;color:#dc2626}}
.eua-dday.mid{{background:#fef3c7;color:#d97706}}
.eua-dday.far{{background:#e0f2fe;color:#0369a1}}
.eua-note{{font-size:.68rem;color:#9ca3af}}

/* 안내 박스 접기 */
.guide-collapse{{border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-top:.5rem}}
.guide-toggle{{width:100%;display:flex;justify-content:space-between;align-items:center;
               padding:.55rem .9rem;background:#f8faff;border:none;cursor:pointer;
               font-size:.76rem;font-weight:600;color:#374151;font-family:inherit;text-align:left}}
.guide-toggle:hover{{background:#eff6ff;color:#1e3a8a}}
.guide-toggle-arrow{{font-size:.7rem;color:#9ca3af;transition:transform .2s}}
.guide-toggle.open .guide-toggle-arrow{{transform:rotate(180deg)}}
.guide-collapse-body{{display:none;padding:.65rem .9rem .75rem}}
.guide-collapse-body.open{{display:block}}
.guide-title{{font-size:.8rem;font-weight:600;color:#1e3a8a;margin-bottom:.6rem}}
.guide-steps{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:.5rem}}
.guide-step{{display:flex;align-items:center;gap:5px;font-size:.75rem;color:#374151;
             background:#f8faff;border:1px solid #e5e7eb;border-radius:6px;padding:4px 9px}}
.guide-num{{display:inline-flex;align-items:center;justify-content:center;
            width:16px;height:16px;border-radius:50%;background:#2563eb;
            color:#fff;font-size:.62rem;font-weight:700;flex-shrink:0}}
.guide-note{{font-size:.7rem;color:#9ca3af;margin-top:.25rem}}

/* 점심 CTA + 섹션 */
.lunch-cta{{display:block;padding:7px 18px;border-radius:6px;
            border:1.5px solid #f97316;background:#fff7ed;color:#ea580c;
            text-decoration:none;text-align:center;width:100%;
            font-family:inherit;font-weight:600;font-size:.8rem;
            transition:background .12s,color .12s;white-space:nowrap}}
.lunch-cta:hover{{background:#ea580c;color:#fff}}
.lunch-section{{display:none;margin:1rem 0;border-radius:12px;overflow:hidden;border:2px solid #fed7aa}}
.lunch-section.open{{display:block}}
.lunch-header{{background:#ea580c;color:#fff;padding:.65rem 1.1rem;
               font-size:.85rem;font-weight:700;cursor:pointer;
               display:flex;justify-content:space-between;align-items:center}}
.lunch-row{{cursor:pointer;padding:.6rem 1.1rem;font-size:.8rem;
            display:flex;justify-content:space-between;align-items:center;
            border-bottom:1px solid rgba(0,0,0,.06);font-weight:600}}
.lunch-row:last-child{{border-bottom:none}}
.lunch-row-arrow{{font-size:.72rem;color:#6b7280;transition:transform .2s}}
.lunch-row.open .lunch-row-arrow{{transform:rotate(90deg)}}
.lunch-content{{display:none;padding:.55rem 1.1rem .7rem;font-size:.78rem;line-height:1.7}}
.lunch-content.open{{display:block}}
.lunch-r1{{background:#fff7ed;color:#9a3412}}.lunch-r2{{background:#fef3c7;color:#92400e}}
.lunch-r3{{background:#ecfdf5;color:#065f46}}.lunch-r4{{background:#eff6ff;color:#1e40af}}
.lunch-r5{{background:#fdf4ff;color:#6b21a8}}.lunch-r6{{background:#fff1f2;color:#9f1239}}

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
    <div class="header-left">
      <div class="brand">
        <span class="brand-name">🚢 KLCSM Desk</span>
        <span class="brand-sub">해운 브리핑</span>
      </div>
      <a class="lunch-cta" href="./lunch">🍱 식신e식권 식당 찾기</a>
    </div>
    <div class="weather-word-wrap">
      <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap">
        <div class="weather-bar" id="weatherBar"></div>
        <button class="weather-setting-btn" id="weatherSettingBtn" title="날씨 지역 설정">⚙️</button>
      </div>
      {word_html}
    </div>
    <!-- 날씨 설정 모달 -->
    <div class="weather-modal-overlay" id="weatherModalOverlay">
      <div class="weather-modal">
        <div class="weather-modal-title">🌍 날씨 지역 설정</div>
        <div id="weatherCityInputs"></div>
        <div style="font-size:.68rem;color:#9ca3af;margin-top:6px">위도·경도는 Google Maps에서 확인 가능</div>
        <div class="weather-modal-btns">
          <button id="weatherModalCancel">취소</button>
          <button class="weather-modal-save" id="weatherModalSave">저장</button>
        </div>
      </div>
    </div>
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
  </div>
  <div class="my-site-grid droptarget" id="mySiteGrid">
    <div class="my-empty" id="myEmpty">아래 섹션의 ＋ 버튼을 클릭해서 추가하세요</div>
  </div>

  <div class="sec-label">📰 최신 해운 뉴스</div>
  {sm_news_html}
  <div class="news-grid">
    {news_html}
  </div>

  <div class="sites-section">
    <div class="sec-label">🔗 주요 사이트</div>

    <!-- 운임지수/연료환경/통계 접기 패널 -->
    <div class="collapse-panel">
      <button class="collapse-toggle" id="siteToggleBtn">
        📂 운임지수 · 연료·환경 · 통계·보고서 펼치기 <span class="collapse-arrow">▾</span>
      </button>
      <div class="collapse-body" id="siteCollapseBody">
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
          <div class="site-link-item draggable" draggable="true" data-name="TradLinx 해운 블로그" data-url="https://www.tradlinx.com/blog/"><a href="https://www.tradlinx.com/blog/" target="_blank">TradLinx 해운 블로그</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
          <div class="site-link-item draggable" draggable="true" data-name="탱커 TCE·Worldscale" data-url="https://www.spotmarketcap.com/shipping"><a href="https://www.spotmarketcap.com/shipping" target="_blank">탱커 TCE·Worldscale</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
        </div>

        <!-- 연료·환경 -->
        <div class="site-group-label">⛽ 연료·환경</div>
        <div class="site-link-row" id="group-env">
          <div class="site-link-item draggable" draggable="true" data-name="글로벌 벙커유 — Ship&Bunker" data-url="https://shipandbunker.com/prices"><a href="https://shipandbunker.com/prices" target="_blank">⛽ 글로벌 벙커유 — Ship&Bunker</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
          <div class="site-link-item draggable" draggable="true" data-name="VLSFO 실시간 가격 — vlsfo.com" data-url="https://vlsfo.com/"><a href="https://vlsfo.com/" target="_blank">🛢️ VLSFO 실시간 가격 — vlsfo.com</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
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
          <div class="site-link-item draggable" draggable="true" data-name="EMSA THETIS MRV" data-url="https://thetis.emsa.europa.eu/"><a href="https://thetis.emsa.europa.eu/" target="_blank">🇪🇺 EMSA THETIS MRV</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
          <div class="site-link-item draggable" draggable="true" data-name="KR GEARS (탈탄소 플랫폼)" data-url="https://gears.krs.co.kr/"><a href="https://gears.krs.co.kr/" target="_blank">🔰 KR GEARS</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
          <div class="site-link-item draggable" draggable="true" data-name="KOMSA SEM (온실가스 시스템)" data-url="https://sem.komsa.or.kr/"><a href="https://sem.komsa.or.kr/" target="_blank">♻️ KOMSA SEM</a><span class="pin-dot" title="내 사이트에 추가">＋</span></div>
        </div>

        <!-- 4번: 직접 추가 버튼 - 접기 패널 안으로 이동 -->
        <div style="margin:.5rem 0 .25rem;display:flex;align-items:center;gap:10px">
          <button class="direct-add-btn" id="addSiteBtn">＋ 내 사이트에 직접 추가</button>
          <span style="font-size:.67rem;color:#86868b">URL을 직접 입력해서 내 사이트에 추가</span>
        </div>
      </div>
    </div>

    <!-- 주요 해운 사이트 - 국내/해외 신문만 (항상 표시) -->
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
      <a class="site-card" href="http://www.haesanews.com/" target="_blank">
        <div class="site-card-name">해사신문</div><div class="site-card-sub">해운·해사·환경 전문지</div></a>
      <a class="site-card" href="https://www.haesainfo.com/news/articleList.html?view_type=sm" target="_blank">
        <div class="site-card-name">해사정보신문</div><div class="site-card-sub">해운·항만·조선 뉴스</div></a>
      <a class="site-card" href="https://maritime-executive.com/" target="_blank">
        <div class="site-card-name">Maritime Executive</div><div class="site-card-sub">해외 해운 전문 (영문)</div></a>
      <a class="site-card" href="https://splash247.com/" target="_blank">
        <div class="site-card-name">Splash247</div><div class="site-card-sub">해외 해운 뉴스 (영문)</div></a>
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

  <!-- EUA D-Day + 안내 박스 (계열사와 간격) -->
  <div style="margin-top:1.5rem">
    <div class="eua-box">
      <div class="eua-title">⚠️ 중요 D-DAY — 환경규제 & 선물 만기</div>
      <div class="eua-body" id="euaDday"></div>
      <div class="eua-note">IMO DCS·EU-ETS·FuelEU·EUA 선물 만기일 기준 (KST 자정 기준)</div>
    </div>

    <!-- 점심 메뉴 섹션 -->
    <div class="lunch-section" id="lunch-section">
      <div class="lunch-header" onclick="this.parentElement.classList.toggle('open')">
        🍱 점심 메뉴 정하기 <span>▾</span>
      </div>
      <div class="lunch-row lunch-r1" onclick="this.nextElementSibling.classList.toggle('open');this.classList.toggle('open')">
        🎲 오늘의 추천 메뉴 (랜덤 뽑기) <span class="lunch-row-arrow">▶</span>
      </div>
      <div class="lunch-content lunch-r1">
        <div id="lunchRandom" style="font-size:1rem;font-weight:700;padding:.3rem 0"></div>
        <button onclick="pickLunch()" style="margin-top:.4rem;padding:4px 14px;border-radius:6px;border:1px solid #ea580c;background:#fff;color:#ea580c;cursor:pointer;font-family:inherit;font-size:.75rem">다시 뽑기 🎲</button>
      </div>
      <div class="lunch-row lunch-r2" onclick="this.nextElementSibling.classList.toggle('open');this.classList.toggle('open')">
        🗳️ 팀원 투표하기 <span class="lunch-row-arrow">▶</span>
      </div>
      <div class="lunch-content lunch-r2">
        <div id="lunchVotes" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:.5rem"></div>
        <div style="font-size:.72rem;color:#92400e">※ 이 브라우저에만 저장됩니다</div>
      </div>
      <div class="lunch-row lunch-r3" onclick="this.nextElementSibling.classList.toggle('open');this.classList.toggle('open')">
        📍 근처 맛집 찾기 <span class="lunch-row-arrow">▶</span>
      </div>
      <div class="lunch-content lunch-r3">
        <a href="https://map.naver.com/p/search/화성시+점심" target="_blank" style="color:#065f46;text-decoration:underline">네이버지도 — 근처 음식점 검색 ↗</a><br>
        <a href="https://www.google.com/maps/search/점심+화성+경기" target="_blank" style="color:#065f46;text-decoration:underline">Google Maps 검색 ↗</a>
      </div>
    </div>

    <!-- 안내 박스 - 접기 가능 -->
    <div class="guide-collapse">
      <button class="guide-toggle" id="guideToggleBtn">
        💡 KLCSM Desk를 크롬 시작 페이지로 설정하는 방법
        <span class="guide-toggle-arrow">▾</span>
      </button>
      <div class="guide-collapse-body" id="guideCollapseBody">
        <div class="guide-steps">
          <div class="guide-step"><span class="guide-num">1</span>크롬 우측 상단 <b>⋮</b> (점 세 개) 클릭</div>
          <div class="guide-step"><span class="guide-num">2</span><b>설정</b> 클릭</div>
          <div class="guide-step"><span class="guide-num">3</span>좌측 메뉴 <b>시작 그룹</b> 선택</div>
          <div class="guide-step"><span class="guide-num">4</span><b>특정 페이지 또는 페이지 집합 열기</b> 선택</div>
          <div class="guide-step"><span class="guide-num">5</span><b>새 페이지 추가</b> 후 이 페이지 URL 입력 → 저장</div>
        </div>
        <div class="guide-note">크롬을 열 때마다 KLCSM Desk가 자동으로 표시됩니다. 뉴스와 지수는 매일 08:00 KST에 자동 업데이트됩니다.</div>
      </div>
    </div>
  </div>

  <div style="text-align:center;padding:.75rem 0 .25rem">
    <a href="https://docs.google.com/forms/d/e/1FAIpQLSf02QLTcsvaylNg34cFowe7lQlFZT3H6bZHKFOo9X4zoM-bcQ/viewform?usp=publish-editor"
       target="_blank"
       style="display:inline-block;padding:8px 20px;border-radius:6px;
              background:#f1f5f9;border:1px solid #e2e8f0;color:#475569;
              font-size:.75rem;font-weight:600;text-decoration:none;
              transition:background .12s,color .12s"
       onmouseover="this.style.background='#1e3a8a';this.style.color='#fff'"
       onmouseout="this.style.background='#f1f5f9';this.style.color='#475569'">
      💬 피드백 보내기
    </a>
  </div>

  <div class="footer">
    {DATE_STR} · {TIME_STR} KST &nbsp;|&nbsp; KLCSM Desk · 매일 08:00 자동 업데이트 · GitHub Pages
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

  // ── 주요사이트 접기 패널
  const siteToggleBtn = document.getElementById('siteToggleBtn');
  const siteCollapseBody = document.getElementById('siteCollapseBody');
  if (siteToggleBtn && siteCollapseBody) {{
    siteToggleBtn.addEventListener('click', () => {{
      const isOpen = siteCollapseBody.classList.toggle('open');
      siteToggleBtn.classList.toggle('open', isOpen);
      siteToggleBtn.innerHTML = isOpen
        ? '📂 운임지수 · 연료·환경 · 통계·보고서 접기 <span class="collapse-arrow">▾</span>'
        : '📂 운임지수 · 연료·환경 · 통계·보고서 펼치기 <span class="collapse-arrow">▾</span>';
    }});
  }}

  // ── SM뉴스 그리드 항상 2열 고정 (cols3 제거)

  // ── 점심 메뉴 랜덤 뽑기
  const LUNCH_MENUS = ['한식 백반','삼겹살','순두부찌개','된장찌개','비빔밥','냉면','국밥','칼국수','짜장면','짬뽕','돈까스','파스타','샌드위치','초밥','샐러드','피자','햄버거','곱창','닭갈비','부대찌개'];
  function pickLunch() {{
    const el = document.getElementById('lunchRandom');
    if (el) el.textContent = LUNCH_MENUS[Math.floor(Math.random()*LUNCH_MENUS.length)] + ' 🍽️';
  }}
  pickLunch();

  // 투표 버튼 생성
  const votesEl = document.getElementById('lunchVotes');
  const VOTE_KEY = 'klcsm_lunch_votes';
  function getVotes() {{ try {{ return JSON.parse(localStorage.getItem(VOTE_KEY)) || {{}}; }} catch(e) {{ return {{}}; }} }}
  function saveVotes(v) {{ localStorage.setItem(VOTE_KEY, JSON.stringify(v)); }}
  function renderVotes() {{
    if (!votesEl) return;
    const v = getVotes();
    votesEl.innerHTML = LUNCH_MENUS.slice(0,8).map(m =>
      `<button onclick="castVote('${{m}}')" style="padding:3px 10px;border-radius:5px;border:1px solid #d97706;background:#fef3c7;color:#92400e;cursor:pointer;font-family:inherit;font-size:.75rem">
        ${{m}} ${{v[m] ? '('+v[m]+')' : ''}}
      </button>`
    ).join('');
  }}
  function castVote(menu) {{
    const v = getVotes(); v[menu] = (v[menu]||0)+1; saveVotes(v); renderVotes();
  }}
  renderVotes();

  // ── 3번: 전체 뉴스 중복 제거 (국내↔해외 포함)
  (function() {{
    const allRows = document.querySelectorAll('.news-row');
    const seen = new Set();
    allRows.forEach(row => {{
      const titleEl = row.querySelector('.news-title');
      if (!titleEl) return;
      const key = titleEl.textContent.replace(/[^\\w가-힣]/g,'').slice(0,15);
      if (seen.has(key)) {{
        row.style.display = 'none';
      }} else {{
        seen.add(key);
      }}
    }});
  }})();
  const guideBtn = document.getElementById('guideToggleBtn');
  const guideBody = document.getElementById('guideCollapseBody');
  if (guideBtn && guideBody) {{
    guideBtn.addEventListener('click', () => {{
      const isOpen = guideBody.classList.toggle('open');
      guideBtn.classList.toggle('open', isOpen);
    }});
  }}

  // ── 날씨 위젯 (Open-Meteo + Windy 연결)
  (function() {{
    const WI = {{0:'☀️',1:'🌤️',2:'⛅',3:'☁️',45:'🌫️',48:'🌫️',
      51:'🌦️',53:'🌦️',55:'🌧️',61:'🌧️',63:'🌧️',65:'🌧️',
      71:'🌨️',73:'🌨️',75:'❄️',80:'🌦️',81:'🌧️',82:'⛈️',95:'⛈️',96:'⛈️',99:'⛈️'}};
    const DEFAULT_CITIES = [
      {{name:'부산', lat:35.1796, lon:129.0756}},
      {{name:'상하이', lat:31.2304, lon:121.4737}},
      {{name:'싱가포르', lat:1.3521, lon:103.8198}},
    ];
    const STORE_KEY = 'klcsm_weather_cities';
    function getCities() {{
      try {{ const s = localStorage.getItem(STORE_KEY); return s ? JSON.parse(s) : DEFAULT_CITIES; }}
      catch(e) {{ return DEFAULT_CITIES; }}
    }}
    function saveCities(arr) {{ try {{ localStorage.setItem(STORE_KEY, JSON.stringify(arr)); }} catch(e) {{}} }}

    async function fetchWeather(lat, lon) {{
      const url = `https://api.open-meteo.com/v1/forecast?latitude=${{lat}}&longitude=${{lon}}&current=temperature_2m,weathercode&timezone=auto`;
      const r = await fetch(url);
      const d = await r.json();
      return {{ temp: Math.round(d.current.temperature_2m), code: d.current.weathercode }};
    }}

    async function renderWeather() {{
      const cities = getCities();
      const bar = document.getElementById('weatherBar');
      if (!bar) return;
      bar.innerHTML = cities.map((c, i) => {{
        const windyUrl = `https://www.windy.com/?${{c.lat}},${{c.lon}},9`;
        return `<div class="weather-chip">
          <a href="${{windyUrl}}" target="_blank" style="text-decoration:none;color:inherit;display:flex;flex-direction:column;align-items:center;gap:1px">
            <span class="weather-chip-icon" id="wicon-${{i}}">⏳</span>
            <span class="weather-chip-name">${{c.name}}</span>
            <span class="weather-chip-temp" id="wtemp-${{i}}">--°</span>
            <span class="weather-chip-link">Windy ↗</span>
          </a>
        </div>`;
      }}).join('');
      cities.forEach(async (c, i) => {{
        try {{
          const w = await fetchWeather(c.lat, c.lon);
          const icon = document.getElementById(`wicon-${{i}}`);
          const temp = document.getElementById(`wtemp-${{i}}`);
          if (icon) icon.textContent = WI[w.code] || '🌡️';
          if (temp) temp.textContent = `${{w.temp}}°`;
        }} catch(e) {{}}
      }});
    }}

    // 설정 모달
    const overlay = document.getElementById('weatherModalOverlay');
    const settingBtn = document.getElementById('weatherSettingBtn');
    const saveBtn = document.getElementById('weatherModalSave');
    const cancelBtn = document.getElementById('weatherModalCancel');

    function openModal() {{
      const cities = getCities();
      const inp = document.getElementById('weatherCityInputs');
      inp.innerHTML = cities.map((c, i) => `
        <div class="weather-city-row">
          <input id="wm-name-${{i}}" value="${{c.name}}" placeholder="도시명">
          <input id="wm-lat-${{i}}" value="${{c.lat}}" placeholder="위도" style="width:80px">
          <input id="wm-lon-${{i}}" value="${{c.lon}}" placeholder="경도" style="width:80px">
        </div>`).join('');
      overlay.classList.add('open');
    }}
    function closeModal() {{ overlay.classList.remove('open'); }}

    if (settingBtn) settingBtn.addEventListener('click', openModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    if (overlay) overlay.addEventListener('click', e => {{ if(e.target===overlay) closeModal(); }});
    if (saveBtn) saveBtn.addEventListener('click', () => {{
      const cities = getCities();
      cities.forEach((c, i) => {{
        const name = document.getElementById(`wm-name-${{i}}`)?.value.trim();
        const lat  = parseFloat(document.getElementById(`wm-lat-${{i}}`)?.value);
        const lon  = parseFloat(document.getElementById(`wm-lon-${{i}}`)?.value);
        if (name && !isNaN(lat) && !isNaN(lon)) cities[i] = {{name, lat, lon}};
      }});
      saveCities(cities);
      closeModal();
      renderWeather();
    }});

    renderWeather();
  }})();

  (function() {{
    const euaEl = document.getElementById('euaDday');
    if (!euaEl) return;
    const now = new Date();
    const yr = now.getFullYear();

    // EUA 선물 만기일: 매년 12월 세 번째 월요일
    function euaExpiry(y) {{
      const d = new Date(y, 11, 1);
      const dow = d.getDay();
      const firstMon = dow <= 1 ? 1 + (1 - dow + 7) % 7 : 1 + (8 - dow);
      return new Date(y, 11, firstMon + 14);
    }}

    // 고정 연간 일정 (2026~2027)
    const schedules = [];
    [yr, yr+1].forEach(y => {{
      schedules.push(
        {{label: `FuelEU Maritime 보고서 마감 (${{y}})`, date: new Date(y, 0, 31)}},
        {{label: `IMO DCS·EU-ETS 배출량 리포트 마감 ★ (${{y}})`, date: new Date(y, 2, 31)}},
        {{label: `THETIS-MRV 검증 마킹 데드라인 (${{y}})`, date: new Date(y, 3, 30)}},
        {{label: `IMO DCS 운항적합증서(SoC) 비치 마감 (${{y}})`, date: new Date(y, 4, 31)}},
        {{label: `EU-ETS 탄소배출권(EUA) 납부 마감 (${{y}})`, date: new Date(y, 8, 30)}},
        {{label: `EUA 선물 만기일 (${{y}})`, date: euaExpiry(y)}}
      );
    }});
    // 해운·조선 주요 행사 (격년 개최, 확정 일정만)
    const events = [
      {{label: 'SMM 2026 — 함부르크 국제조선해양박람회', date: new Date(2026, 8, 1)}},
      {{label: 'Nor-Shipping 2027 — 오슬로 국제해운박람회', date: new Date(2027, 5, 7)}},
      {{label: 'Europort 2027 — 로테르담 국제해양산업전', date: new Date(2027, 10, 2)}},
    ];
    schedules.push(...events);

    // 오늘 이후 일정만 필터 + 날짜 오름차순 정렬 + 2027년까지
    const upcoming = schedules
      .filter(s => s.date >= now && s.date.getFullYear() <= 2027)
      .sort((a, b) => a.date - b.date);

    euaEl.innerHTML = upcoming.map(s => {{
      const diff = Math.ceil((s.date - now) / 86400000);
      const cls = diff <= 30 ? 'near' : diff <= 90 ? 'mid' : 'far';
      const label = diff === 0 ? 'D-DAY' : `D-${{diff}}`;
      const dateStr = s.date.toLocaleDateString('ko-KR', {{year:'numeric',month:'long',day:'numeric'}});
      return `<div class="eua-item">
        <span class="eua-date">${{dateStr}}</span>
        <span class="eua-year" style="flex:1;color:#374151">${{s.label}}</span>
        <span class="eua-dday ${{cls}}">${{label}}</span>
      </div>`;
    }}).join('') || '<div style="color:#9ca3af;font-size:.75rem;padding:.5rem">예정된 일정이 없습니다</div>';
  }})();
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

    # SM뉴스: 매일 수집 (3일치 필터는 get_sm_news 내부에서 처리)
    sm_news = get_sm_news()

    idx_cnt = sum(1 for v in indices.values() if v["value"] != "—")
    print(f"  지수: {idx_cnt}개 수집")
    for k, v in indices.items():
        print(f"    {k}: {v['value']} {v.get('change','')} ({v.get('date','')})")
    print(f"  세부노선: KDCI {len(kdci_routes)}개 / KCCI {len(kcci_routes)}개 / NCFI {len(ncfi_routes)}개")
    ko_cnt = sum(1 for n in news if n["source"] == "구글뉴스")
    en_cnt = sum(1 for n in news if n["source"] == "해외뉴스")
    print(f"  뉴스: 국내 {ko_cnt}건 / 해외 {en_cnt}건")
    print(f"  SM계열사 뉴스: {len(sm_news)}건")

    html = build_html(indices, kdci_routes, kcci_routes, ncfi_routes, news, sm_news)
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
