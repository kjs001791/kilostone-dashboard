"""
Streamlit CSS 스타일 정의
"""
from .config import THEME

def get_css():
    """전체 CSS 스타일 반환"""
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Teko:wght@700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');

    /* [기본] 전체 폰트 및 배경 설정 */
    .stApp {{
        background-color: {THEME['bg_main']};
        font-family: 'Roboto', sans-serif;
    }}
    
    /* [사이드바] */
    [data-testid="stSidebar"] {{
        background-color: {THEME['bg_sidebar']};
        border-right: 1px solid {THEME['border']};
        width: 235px !important;
    }}
    div[data-testid="stSidebar"] > div:nth-child(2) {{ display: none; }}
    
    .logo-text {{
        font-family: 'Teko', sans-serif; 
        font-size: 40px !important; 
        font-weight: 700;
        font-style: italic; 
        color: #e0e0e0; 
        text-align: center; 
        line-height: 0.8;
        margin-top: -10px; 
        margin-bottom: 20px;
        letter-spacing: -1px; 
        white-space: nowrap;
    }}

    /* [탭 디자인] */
    .stTabs [data-baseweb="tab-list"] {{
        background-color: transparent;
        border-bottom: 1px solid {THEME['border']};
        gap: 24px;
        padding-bottom: 0px;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        height: 40px;
        background-color: transparent;
        border: none;
        color: {THEME['text_sub']};
        font-size: 14px;
        font-weight: 500;
        padding: 0 0 10px 0;
    }}

    .stTabs [aria-selected="true"] {{
        color: #8AB4F8 !important; 
    }}
    
    div[data-baseweb="tab-highlight"] {{
        background-color: #8AB4F8 !important;
    }}
    
    .stTabs [data-baseweb="tab"]:hover {{
        color: {THEME['text_main']};
    }}

    /* [KPI 컨테이너] */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: #1E1E1E;
        border: 1px solid #3C4043;
        border-radius: 12px;
        padding: 20px;
    }}

    .kpi-title {{
        color: {THEME['text_sub']};
        font-size: 14px;
        margin-bottom: 4px;
        text-align: center;
    }}
    
    .kpi-value {{
        color: {THEME['text_main']};
        font-size: 32px;
        font-weight: 700;
        text-align: center;
        white-space: nowrap;
    }}
    
    .kpi-delta {{
        font-size: 13px;
        margin-top: 4px;
        text-align: center;
        display: flex;
        justify-content: center;
        gap: 5px;
    }}

    .chart-header {{
        color: {THEME['text_sub']};
        font-size: 16px;
        font-weight: 500;
        margin-bottom: 10px;
        margin-top: 20px;
        padding-left: 5px;
        border-left: 3px solid {THEME['accent_primary']};
        line-height: 1;
    }}

    [data-testid="stDataFrame"] {{
        background-color: transparent;
    }}
    
    hr {{
        border-color: {THEME['border']};
    }}

    /* 차단/경고 메시지 스타일 */
    .blocked-warning {{
        background: linear-gradient(135deg, #2d1f1f 0%, #1a1a1a 100%);
        border: 2px solid {THEME['accent_red']};
        border-radius: 12px;
        padding: 30px;
        text-align: center;
        margin: 50px auto;
        max-width: 500px;
    }}
    
    .blocked-icon {{
        font-size: 48px;
        margin-bottom: 15px;
    }}
    
    .blocked-title {{
        color: {THEME['accent_red']};
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 10px;
    }}
    
    .blocked-message {{
        color: {THEME['text_sub']};
        font-size: 14px;
        line-height: 1.6;
    }}
    
    .attempts-warning {{
        background-color: rgba(253, 214, 99, 0.1);
        border: 1px solid {THEME['accent_yellow']};
        border-radius: 8px;
        padding: 10px 15px;
        margin-top: 10px;
        text-align: center;
    }}
    
    .attempts-text {{
        color: {THEME['accent_yellow']};
        font-size: 14px;
        font-weight: 500;
    }}
    </style>
    """