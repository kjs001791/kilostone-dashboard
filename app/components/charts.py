"""
Plotly 차트 스타일링 헬퍼
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import THEME


def create_clean_chart(fig, height=300):
    """깔끔한 다크 테마 차트 생성"""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=0, r=0, t=20, b=20),
        xaxis=dict(
            showgrid=False, 
            color=THEME['text_sub'], 
            gridcolor=THEME['border']
        ),
        yaxis=dict(
            showgrid=True, 
            gridcolor=THEME['border'], 
            color=THEME['text_sub'], 
            zeroline=False
        ),
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="right", 
            x=1, 
            font=dict(color=THEME['text_sub'])
        ),
        hovermode="x unified"
    )
    return fig