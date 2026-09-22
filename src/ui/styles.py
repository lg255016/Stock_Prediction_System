from typing import Any, Dict

# 金融機構級色彩定義 (嚴格區分台股與美股習慣)
COLOR_TAIWAN_UP = "#FF4B4B"    # 台股紅漲
COLOR_TAIWAN_DOWN = "#00C853"  # 台股綠跌

COLOR_US_UP = "#00C853"        # 美股綠漲
COLOR_US_DOWN = "#FF4B4B"      # 美股紅跌

COLOR_NEUTRAL = "#888888"
COLOR_ACCENT = "#2962FF"       # 科技藍
COLOR_CARD_BG = "#1E222D"      # 卡片深色背景
COLOR_BORDER = "#2B313F"       # 邊框灰色


def get_market_colors(market: str = "TW") -> Dict[str, str]:
    """取得對應市場之漲跌色彩語彙"""
    if str(market).upper() == "US":
        return {
            "up": COLOR_US_UP,
            "down": COLOR_US_DOWN,
            "up_label": "漲 (綠)",
            "down_label": "跌 (紅)",
        }
    return {
        "up": COLOR_TAIWAN_UP,
        "down": COLOR_TAIWAN_DOWN,
        "up_label": "漲 (紅)",
        "down_label": "跌 (綠)",
    }


# 深色模式自訂 CSS 樣式表
DARK_THEME_CSS = """
<style>
    /* 全域深色背景微調 */
    .stApp {
        background-color: #0E1117;
        color: #E0E3EB;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* 側邊欄深色美化 */
    [data-testid="stSidebar"] {
        background-color: #131722;
        border-right: 1px solid #2B313F;
    }
    
    /* 卡片容器樣式 */
    .kpi-card {
        background-color: #1E222D;
        border: 1px solid #2B313F;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .kpi-card:hover {
        border-color: #2962FF;
        transform: translateY(-2px);
    }
    
    .kpi-title {
        font-size: 13px;
        color: #848E9C;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 4px;
        line-height: 1.2;
    }
    
    .kpi-delta {
        font-size: 13px;
        font-weight: 600;
    }
    
    .badge-tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
    }
</style>
"""


def render_kpi_card_html(
    title: str,
    value: str,
    delta: str = "",
    is_positive: bool = True,
    icon: str = "📈",
    badge: str = "",
    market: str = "TW"
) -> str:
    """
    生成標準金融終端風格之 KPI 卡片 HTML。
    """
    colors = get_market_colors(market)
    delta_color = colors["up"] if is_positive else colors["down"]
    badge_bg = "rgba(255, 75, 75, 0.15)" if is_positive else "rgba(0, 200, 83, 0.15)"
    
    badge_html = f'<span class="badge-tag" style="background-color: {badge_bg}; color: {delta_color};">{badge}</span>' if badge else ""
    delta_html = f'<span class="kpi-delta" style="color: {delta_color};">{delta}</span>' if delta else ""

    return f"""
    <div class="kpi-card">
        <div class="kpi-title">
            <span>{icon} {title}</span>
            {badge_html}
        </div>
        <div class="kpi-value">{value}</div>
        <div>{delta_html}</div>
    </div>
    """
