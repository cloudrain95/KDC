# ============================================================
# AI 기반 KDC 분류기호 예측 지원 시스템
# Streamlit 웹앱 버전
# ============================================================

import streamlit as st
import requests
import xml.etree.ElementTree as ET
from collections import Counter
import concurrent.futures
import time

# ── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="KDC 분류기호 예측 시스템",
    page_icon="📚",
    layout="wide"
)

# ── API 키 (secrets에서 읽기) ────────────────────────────────
API_NL           = st.secrets.get("API_NL", "ce6f898f70ee98f87065b7a4a6e65ba7145d3882d24ae822d3b81059da3f0eac")
API_NARULIB      = st.secrets.get("API_NARULIB", "67a5f80ed77ba3cd33b0928c534197fb9ac44712b5ccbf320a7f227e623893ed")
API_DATA4GOV     = st.secrets.get("API_DATA4GOV", "f1583630c8a21253bc9c5d5e58bc03b2bbdd6794a4c47ad0fe69313413a65134")
ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")

# ── 브라우저 헤더 ────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.nl.go.kr/",
}

# ── KDC 분류명 ───────────────────────────────────────────────
KDC_NAME = {
    "0":"총류","000":"총류","004":"컴퓨터과학","020":"문헌정보학",
    "1":"철학","100":"철학","180":"심리학","189":"자기계발","190":"윤리학",
    "2":"종교","200":"종교","220":"불교","230":"기독교",
    "3":"사회과학","300":"사회과학","302":"사회적상호작용",
    "304":"사회문제·사회운동","320":"경제학","325":"경영·진로",
    "330":"사회학","340":"정치학","350":"행정학","360":"법학",
    "370":"교육학","378":"평생교육",
    "4":"자연과학","400":"자연과학",
    "5":"기술과학","500":"기술과학","510":"의학","590":"생활과학",
    "6":"예술","600":"예술","670":"음악","690":"스포츠",
    "7":"언어","700":"언어","710":"한국어","740":"영어",
    "8":"문학","800":"문학","810":"한국문학",
    "811":"한국시","812":"한국희곡","813":"한국소설","814":"한국수필",
    "820":"중국문학","830":"일본문학","840":"영미문학",
    "9":"역사","900":"역사","910":"아시아사","911":"한국사","990":"전기",
}

KDC_GUIDE = {
    "0":  "총류는 특정 주제에 한정되지 않는 저작(백과사전, 도서관학 등)에 적용합니다.",
    "1":  "철학은 존재·인식·논리·윤리 등 철학적 탐구와 동·서양 사상을 다룬 저작에 적용합니다.",
    "18": "심리학(180)은 인간 행동·정신 연구를, 응용심리·자기계발(189)은 실생활 적용을 다룹니다.",
    "2":  "종교는 신앙·교리·의례 등 종교적 내용을 다룬 저작에 적용합니다.",
    "3":  "사회과학은 사회·경제·정치·법·교육 등 사회 현상을 분석한 저작에 적용합니다.",
    "30": "사회학(330)은 사회 집단·제도를, 사회문제(304)는 사회 비평·현안 저작에 적용합니다.",
    "32": "경제학(320)은 경제이론을, 경영·진로(325)는 직업·커리어·성공 관련 저작에 적용합니다.",
    "37": "교육학(370)은 교육 이론·제도를, 평생교육(378)은 성인·비형식 교육을 다룹니다.",
    "4":  "자연과학은 수학·물리·화학·생명과학 등 자연 현상을 탐구하는 저작에 적용합니다.",
    "5":  "기술과학은 의학·공학·농학·생활과학 등 응용기술을 다룬 저작에 적용합니다.",
    "6":  "예술은 미술·음악·연극·영화·스포츠 등 예술 활동을 다룬 저작에 적용합니다.",
    "7":  "언어는 특정 언어의 문법·어휘·회화 등을 다룬 저작에 적용합니다.",
    "8":  "문학은 내용 주제가 아닌 언어·형식으로 분류합니다. 번역서는 원저 언어 기준입니다.",
    "81": "한국문학(810)은 한국어로 쓰인 문학 저작에 적용합니다.",
    "9":  "역사는 특정 지역·시대의 역사적 사실을 다룬 저작에 적용합니다.",
}

def get_kdc_name(kdc):
    if not kdc:
        return ""
    kdc = kdc.strip()
    for l in [6,5,4,3,2,1]:
        key = kdc[:l].rstrip(".")
        if key in KDC_NAME:
            return KDC_NAME[key]
    return ""

def get_kdc_guide(kdc):
    if not kdc:
        return ""
    for l in [3,2,1]:
        key = kdc[:l]
        if key in KDC_GUIDE:
            return KDC_GUIDE[key]
    return ""

def safe_get(url, params, timeout=20):
    for i in range(2):
        try:
            return requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        except requests.exceptions.Timeout:
            if i == 0:
                time.sleep(2)
            else:
                raise

# ── API 함수들 ───────────────────────────────────────────────
def search_nl_keywords(keywords_str, page_size=30):
    keywords = [k.strip() for k in keywords_str.split("&") if k.strip()]
    if not keywords:
        return []
    base = "https://www.nl.go.kr/NL/search/openApi/search.do"
    params = {
        "key": API_NL,
        "kwd": keywords[0],
        "detailSearch": "true",
        "pageSize": str(page_size),
        "pageNum": "1",
    }
    for i, kw in enumerate(keywords[1:4], 1):
        params[f"f{i}"] = "all"
        params[f"v{i}"] = kw
    try:
        resp = safe_get(base, params)
        resp.encoding = "utf-8"
        root = ET.fromstring(resp.text)
        total = root.findtext(".//total", "0")
        books = []
        for item in root.findall(".//item"):
            if item.findtext("type_name","") not in ("도서","일반도서"):
                continue
            isbn = item.findtext("isbn","").strip()
            kdc  = item.findtext("class_no","").strip()
            if not isbn and not kdc:
                continue
            books.append({
                "title":   item.findtext("title_info","").strip(),
                "author":  item.findtext("author_info","").strip(),
                "year":    item.findtext("pub_year_info","").strip(),
                "isbn":    isbn,
                "nl_kdc":  kdc,
                "nl_kdc_name": item.findtext("kdc_name_1s","").strip(),
            })
        return books, total
    except Exception as e:
        return [], "0"

def fetch_naru_one(isbn):
    result = {"isbn": isbn, "kdc_list": [], "keywords": []}
    if not isbn:
        return result
    try:
        resp = requests.get(
            "http://data4library.kr/api/srchDtlList",
            params={"authKey": API_NARULIB, "isbn13": isbn.replace("-",""),
                    "loaninfoYN": "Y", "format": "json"},
            headers=HEADERS, timeout=15)
        data = resp.json().get("response", {})
        for item in data.get("detail", []):
            kdc = item.get("book", {}).get("class_no", "")
            if kdc:
                result["kdc_list"].append(kdc)
    except Exception:
        pass
    try:
        resp = requests.get(
            "http://data4library.kr/api/keywordList",
            params={"authKey": API_NARULIB, "isbn13": isbn.replace("-",""),
                    "additionalYN": "Y", "format": "json"},
            headers=HEADERS, timeout=15)
        items = resp.json().get("response", {}).get("items", [])
        result["keywords"] = [k.get("item",{}).get("word","")
                               for k in items if k.get("item",{}).get("word")]
    except Exception:
        pass
    return result

def fetch_naru_batch(books, max_workers=5):
    isbns = [b["isbn"] for b in books if b.get("isbn")]
    if not isbns:
        return {}
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_isbn = {executor.submit(fetch_naru_one, isbn): isbn for isbn in isbns}
        for future in concurrent.futures.as_completed(future_to_isbn):
            isbn = future_to_isbn[future]
            try:
                results[isbn] = future.result()
            except Exception:
                results[isbn] = {"isbn": isbn, "kdc_list": [], "keywords": []}
    return results

def analyze_kdc(books, naru_results):
    nl_kdcs, naru_kdcs, all_keywords, book_summary = [], [], [], []
    for book in books:
        isbn   = book.get("isbn","")
        nl_kdc = book.get("nl_kdc","")
        if nl_kdc:
            nl_kdcs.append(nl_kdc)
        naru = naru_results.get(isbn, {})
        naru_kdc_list = naru.get("kdc_list",[])
        naru_kdcs.extend(naru_kdc_list)
        all_keywords.extend(naru.get("keywords",[]))
        rep_kdc = naru_kdc_list[0] if naru_kdc_list else nl_kdc
        if rep_kdc:
            book_summary.append({
                "title":    book["title"],
                "kdc":      rep_kdc,
                "kdc_name": get_kdc_name(rep_kdc),
                "source":   "정보나루" if naru_kdc_list else "국중",
                "keywords": naru.get("keywords",[])[:5],
            })
    def normalize(kdc):
        return kdc[:3] if len(kdc) >= 3 else kdc
    all_kdcs = nl_kdcs + naru_kdcs
    kdc_counter = Counter([normalize(k) for k in all_kdcs if k])
    return {
        "kdc_counter":    kdc_counter,
        "book_summary":   book_summary,
        "all_keywords":   list(set(all_keywords)),
        "total_kdc_count": len(all_kdcs),
    }

def predict_claude(keywords_str, analysis):
    if not ANTHROPIC_API_KEY:
        return None
    kdc_dist = "\n".join([
        f"  KDC {kdc} {get_kdc_name(kdc)}: {cnt}건"
        for kdc, cnt in analysis["kdc_counter"].most_common(10)
    ])
    book_list = "\n".join([
        f"  - {b['title'][:40]} → KDC {b['kdc']} {b['kdc_name']} ({b['source']})"
        for b in analysis["book_summary"][:15]
    ])
    top_keywords = ", ".join(analysis["all_keywords"][:20])
    prompt = f"""당신은 KDC(한국십진분류법) 6판 전문 사서입니다.

사용자가 새 도서에 부여할 KDC 분류기호를 예측하고 싶어합니다.
아래는 입력 키워드와 관련된 기존 도서들의 분류 현황입니다.

[입력 키워드]
{keywords_str}

[관련 도서 KDC 분포]
(총 {analysis['total_kdc_count']}건)
{kdc_dist}

[관련 도서 목록 (일부)]
{book_list}

[전국 도서관 키워드]
{top_keywords}

위 데이터를 종합 분석하여 KDC 6판 기준으로 예측 분류기호를 제시해 주세요.

반드시 아래 형식으로 답하세요:

[1순위] KDC XXX.XX (분류명) — 근거: ...
[2순위] KDC XXX.XX (분류명) — 근거: ...
[3순위] KDC XXX.XX (분류명) — 근거: ...

[해설]
분류 원칙 및 주주제 판정 근거를 3~5문장으로 설명하세요.
KDC 6판 적용 기준과 학생 비교 학습을 위한 설명을 포함하세요."""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        data = resp.json()
        text = "".join(c.get("text","") for c in data.get("content",[]))
        return text.strip() if text else None
    except Exception:
        return None

def predict_builtin(keywords_str, analysis):
    kdc_counter = analysis["kdc_counter"]
    if not kdc_counter:
        return None
    top3  = kdc_counter.most_common(3)
    total = analysis["total_kdc_count"]
    lines = []
    medals = ["1순위","2순위","3순위"]
    for i, (kdc, cnt) in enumerate(top3):
        name = get_kdc_name(kdc)
        pct  = round(cnt / total * 100, 1) if total else 0
        lines.append(f"[{medals[i]}] KDC {kdc} ({name}) — 관련 도서 {cnt}건 ({pct}%)")
    lines.append("")
    lines.append("[해설]")
    kdc1  = top3[0][0]
    name1 = get_kdc_name(kdc1)
    guide = get_kdc_guide(kdc1)
    lines.append(f"입력 키워드 '{keywords_str}'와 관련된 도서 {total}건을 분석한 결과,")
    lines.append(f"KDC {kdc1}({name1})이 가장 많이 분류된 번호입니다.")
    if guide:
        lines.append(guide)
    if len(top3) >= 2:
        kdc2, cnt2 = top3[1]
        name2 = get_kdc_name(kdc2)
        lines.append(f"KDC {kdc2}({name2})도 {cnt2}건으로 고려할 수 있습니다.")
    lines.append("※ 다주제 저작은 주주제를 우선하는 원칙을 적용합니다.")
    lines.append("※ 최종 분류 전 목차·내용 직접 확인을 권장합니다.")
    return "\n".join(lines)

# ============================================================
# Streamlit UI
# ============================================================
st.title("📚 AI 기반 KDC 분류기호 예측 지원 시스템")
st.markdown("국립중앙도서관 + 정보나루 + Claude AI 연동")
st.divider()

# 입력 섹션
col1, col2 = st.columns([3, 1])
with col1:
    user_input = st.text_input(
        "🔍 키워드 입력",
        placeholder="예: 개인주의 & 사회비평   /   진로 & 직업 & 성공",
        help="여러 키워드는 & 로 구분하세요 (AND 검색)"
    )
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    run_btn = st.button("분류 예측 시작", type="primary", use_container_width=True)

st.caption("💡 & 기호로 여러 키워드를 AND 검색할 수 있습니다. 예: `개인주의 & 한국사회`")

if run_btn and user_input.strip():
    keywords_str = user_input.strip()

    # STEP 1
    with st.spinner("📖 국립중앙도서관 소장자료 검색 중..."):
        books, total = search_nl_keywords(keywords_str, page_size=30)

    if not books:
        st.error("관련 도서를 찾을 수 없습니다. 키워드를 바꿔 보세요.")
        st.stop()

    st.success(f"✅ 국중 검색 완료: 총 {total}건 중 도서 {len(books)}건 수집")

    # STEP 2
    with st.spinner(f"📡 정보나루 전국 도서관 데이터 수집 중... (ISBN {len([b for b in books if b.get('isbn')])}건)"):
        naru_results = fetch_naru_batch(books, max_workers=5)

    # STEP 3
    with st.spinner("📊 KDC 분포 분석 중..."):
        analysis = analyze_kdc(books, naru_results)

    if not analysis["kdc_counter"]:
        st.error("KDC 데이터를 추출하지 못했습니다.")
        st.stop()

    st.success(f"✅ KDC {len(analysis['kdc_counter'])}종 추출, 총 {analysis['total_kdc_count']}건 분석 완료")

    st.divider()

    # 결과 레이아웃
    left, right = st.columns([1, 1])

    with left:
        # KDC 분포
        st.subheader("📊 관련 도서 KDC 분포")
        total_kdc = analysis["total_kdc_count"]
        for kdc, cnt in analysis["kdc_counter"].most_common(5):
            name = get_kdc_name(kdc)
            pct  = round(cnt / total_kdc * 100, 1) if total_kdc else 0
            st.markdown(f"**KDC {kdc}** {name}")
            st.progress(pct / 100, text=f"{cnt}건 ({pct}%)")

        # 관련 도서 목록
        st.subheader("📚 수집된 관련 도서")
        for b in analysis["book_summary"][:10]:
            with st.expander(f"{b['title'][:40]}"):
                st.markdown(f"**KDC:** {b['kdc']} {b['kdc_name']} `[{b['source']}]`")
                if b["keywords"]:
                    st.markdown(f"**키워드:** {', '.join(b['keywords'][:5])}")

    with right:
        # KDC 예측
        st.subheader("🎯 KDC 분류기호 예측 결과")

        with st.spinner("🤖 AI 분류기호 예측 중..."):
            prediction = predict_claude(keywords_str, analysis)
            method = "Claude AI"
            if not prediction:
                prediction = predict_builtin(keywords_str, analysis)
                method = "내장 지침"

        st.caption(f"해설 방법: {method}")

        if prediction:
            # 순위 파싱해서 카드로 표시
            lines = prediction.split("\n")
            medals = {"[1순위]": "🥇", "[2순위]": "🥈", "[3순위]": "🥉"}
            in_desc = False
            desc_lines = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                matched = False
                for rank, medal in medals.items():
                    if line.startswith(rank):
                        content = line.replace(rank, "").strip()
                        if rank == "[1순위]":
                            st.markdown(f"### {medal} {rank}")
                            st.info(content)
                        elif rank == "[2순위]":
                            st.markdown(f"### {medal} {rank}")
                            st.success(content)
                        else:
                            st.markdown(f"### {medal} {rank}")
                            st.warning(content)
                        matched = True
                        break
                if not matched:
                    if line.startswith("[해설]"):
                        in_desc = True
                    elif in_desc:
                        desc_lines.append(line)

            if desc_lines:
                st.divider()
                st.subheader("📖 해설")
                st.markdown("\n\n".join(desc_lines))

    # 키워드 요약
    if analysis["all_keywords"]:
        st.divider()
        st.subheader("🏷 전국 도서관 키워드")
        kw_text = "  ".join([f"`{k}`" for k in analysis["all_keywords"][:20]])
        st.markdown(kw_text)

elif run_btn and not user_input.strip():
    st.warning("키워드를 입력하세요.")

# 사이드바
with st.sidebar:
    st.markdown("### 📌 사용 방법")
    st.markdown("""
1. 키워드 입력
2. **&** 로 AND 검색
3. **분류 예측 시작** 클릭
4. KDC 1·2·3순위 확인
5. 해설 참고 후 직접 분류와 비교
""")
    st.divider()
    st.markdown("### 🔧 연동 API")
    st.markdown("""
- 국립중앙도서관 소장자료
- 도서관 정보나루
- 공공데이터포털 LOD
- Claude AI
""")
    st.divider()
    st.markdown("### 💡 예시 키워드")
    st.code("개인주의 & 사회비평")
    st.code("진로 & 직업 & 성공")
    st.code("인공지능 & 윤리")
    st.code("한국문학 & 현대소설")
