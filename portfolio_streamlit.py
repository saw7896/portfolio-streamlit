import streamlit as st
import pandas as pd
from pykrx import stock
import datetime
import os

st.set_page_config(page_title="포트폴리오 매니저", layout="wide")

# —————————————————————————————————
# 날짜 및 데이터 로드 (전일 종가 기준)
today = datetime.datetime.today()
yesterday = today - datetime.timedelta(days=1)
date_str = yesterday.strftime("%Y%m%d")

data_path = "kr.csv"
if os.path.exists(data_path):
    raw_df = pd.read_csv(data_path, dtype={'종목코드': str})
    # ★ 여기서 기본 컬럼만 남기고, 나머지(이전 계산 컬럼) 전부 드랍
    kr_df = raw_df[["종목명", "종목코드", "수량", "목표비중(주식내)"]]
else:
    kr_df = pd.DataFrame([
        ["카이카",    "381970", 33872, "12.3%"],
        ["삼양식품",  "003230",   124, "0.05%"],
        ["경동나비엔","009450",  7344, "2.67%"],
        ["더존비즈온","012510",  2261, "0.82%"],
        ["아세아시멘트","183190",44439, "16.14%"],
        ["와이지-원","019210", 90363, "32.81%"],
        ["네오팜",    "092730", 23709, "8.61%"],
        ["삼성전자",  "005930",  5755, "2.09%"],
        ["에이유브랜즈","481070",    0, "0.00%"],
        ["아이센스",  "099190",  9387, "3.41%"],
    ], columns=["종목명", "종목코드", "수량", "목표비중(주식내)"])

# 세션 상태 초기화
if 'kr_df' not in st.session_state:
    st.session_state.kr_df = kr_df
if 'kr_cash' not in st.session_state:
    st.session_state.kr_cash = 581_365_595
if 'stock_ratio' not in st.session_state:
    st.session_state.stock_ratio = 0.9

# —————————————————————————————————
# 가격 조회 함수 (15분 캐시)
@st.cache_data(ttl=900)
def get_price(code):
    try:
        df = stock.get_market_ohlcv_by_date(date_str, date_str, code)
        return int(df["종가"].iloc[0])
    except:
        return 1000

# 메트릭 계산 함수
def calculate_metrics(df, cash, ratio):
    df = df.copy()
    # 1) 현재가, 평가금액
    df['현재가']       = df['종목코드'].apply(get_price)
    df['보유 평가금액'] = df['수량'] * df['현재가']
    total_eval = df['보유 평가금액'].sum()
    nav = total_eval + cash

    # 2) 편입 비중
    df['편입비중(/NAV)']   = df['보유 평가금액'] / nav
    df['편입비중(/주식내)'] = df['보유 평가금액'] / (nav * ratio)

    # 3) 목표비중 → NAV 기준 환산
    pct = df['목표비중(주식내)'].str.rstrip('%').astype(float) / 100
    df['목표비중(/NAV)']       = pct * ratio
    df['신규목표비중(/NAV)']   = pct * ratio   # 변경: (1−ratio) 가 아닌 ratio

    # 4) 증감
    df['증감(목표-목표)(/NAV)'] = df['신규목표비중(/NAV)'] - df['목표비중(/NAV)']
    df['증감(목표-편입)(/NAV)'] = df['목표비중(/NAV)'] - df['편입비중(/NAV)']

    # 5) 목표 평가 금액
    df['목표 평가 금액'] = df['목표비중(/NAV)'] * nav

    # 6) 포맷팅
    df['현재가']         = df['현재가'].map("{:,.0f}".format)
    df['보유 평가금액']  = df['보유 평가금액'].map("{:,.0f}".format)
    df['목표 평가 금액'] = df['목표 평가 금액'].map("{:,.0f}".format)
    for col in [
        '편입비중(/NAV)', '편입비중(/주식내)',
        '목표비중(/NAV)', '신규목표비중(/NAV)',
        '증감(목표-목표)(/NAV)', '증감(목표-편입)(/NAV)'
    ]:
        df[col] = df[col].apply(lambda x: f"{x*100:.1f}%")

    return df, total_eval, cash, nav

# —————————————————————————————————
# 사이드바: 설정 & 매매
with st.sidebar:
    st.header("⚙️ 설정 및 거래")
    opts = ["50%", "60%", "70%", "80%", "90%", "100%"]
    idx = opts.index(f"{int(st.session_state.stock_ratio*100)}%")
    sel = st.selectbox("주식 비중 설정 (%)", opts, index=idx)
    st.session_state.stock_ratio = int(sel.rstrip('%')) / 100

    st.markdown("---")
    st.subheader("🛒 매수/매도 입력")
    ttype = st.radio("거래 종류", ["매수", "매도"], horizontal=True)
    name  = st.text_input("종목명 입력")
    price = st.number_input("단가 (원)", min_value=0)
    qty   = st.number_input("수량",   min_value=1, step=1)

    if st.button("거래 실행") and name:
        df   = st.session_state.kr_df
        cash = st.session_state.kr_cash
        if name in df['종목명'].values:
            i = df[df['종목명']==name].index[0]
            if ttype=="매수":
                df.at[i,'수량'] += qty; cash -= price*qty
            else:
                df.at[i,'수량'] = max(0, df.at[i,'수량']-qty); cash += price*qty
        else:
            new = {"종목명":name,"종목코드":"신규","수량":qty,"목표비중(주식내)":"0.00%"}
            df = pd.concat([df,pd.DataFrame([new])], ignore_index=True)
            if ttype=="매수": cash -= price*qty
        st.session_state.kr_df   = df
        st.session_state.kr_cash = cash
        df[["종목명","종목코드","수량","목표비중(주식내)"]].to_csv(
            data_path, index=False, encoding="utf-8-sig"
        )

# —————————————————————————————————
st.title("📈 포트폴리오 매니저 (김현준M)")

if st.button("🔄 국내 종목 현재가 갱신"):
    st.experimental_rerun()

# 목표비중 에디터
edited = st.data_editor(
    st.session_state.kr_df[["종목명","종목코드","수량","목표비중(주식내)"]],
    column_config={"목표비중(주식내)": st.column_config.TextColumn(help="예: 10.00%")},
    num_rows="dynamic", use_container_width=True
)
st.session_state.kr_df['목표비중(주식내)'] = edited['목표비중(주식내)']
st.session_state.kr_df.to_csv(data_path, index=False, encoding="utf-8-sig")

# 메트릭 계산 & 출력
metrics_df, total_eval, cash, nav = calculate_metrics(
    st.session_state.kr_df, st.session_state.kr_cash, st.session_state.stock_ratio
)
st.dataframe(metrics_df, use_container_width=True)

c1, c2, c3 = st.columns([1.5,1.5,1])
c1.markdown(f"**📊 국내 주식 평가금액:** `{total_eval:,.0f} 원`")
c2.markdown(f"**💵 국내 현금:** `{cash:,.0f} 원`")
c3.markdown(f"**📦 국내 NAV:** `{nav:,.0f} 원`")
