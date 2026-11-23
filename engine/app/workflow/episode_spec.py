"""从用户想法里解析目标集数 —— 集数不能写死。
用户的原话可能是"只做一集""做成三集""共 5 集""一部 10 集短剧"，
也可能完全没提集数 —— 这时按 **1 集** 处理（省 token，逐集推进）。
刻意不把这些当成集数：
- "100 岁""从 1 岁到 100 岁"：年龄跨度
- "每集 200 字"：每集的长度，不是集数
- "第 2 集""第二集太快了"：修改诉求，不是新建规模
- "一部"：部不是集
"""
from __future__ import annotations
import re
DEFAULT_EPISODE_COUNT = 1
MAX_EPISODE_COUNT = 30
_CN_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_UNITS = {"十": 10, "百": 100}
# 数字：阿拉伯数字或中文数字（1-3 位）
_NUM = r"(?:\d{1,3}|[零〇一二两三四五六七八九十百]{1,3})"
# 明确"只要一集"的说法（优先于任何数字）
_ONLY_ONE = re.compile(
    r"(?:只|仅|就|光|单)\s*(?:做|写|来|要|生成|出|整)?\s*一集"
    r"|一集\s*(?:就好|即可|就行|版|的)"
    r"|单集"
)
# 总量型表达："共 3 集""写成 5 集""一部三集短剧"
_TOTAL = re.compile(
    rf"(?:总共|一共|共|合计|总计|整|写|做|来|要|生成|产出|排|分|改(?:成|为)?)\s*{_NUM}\s*集"
    rf"|{_NUM}\s*集\s*(?:的)?\s*(?:竖屏|短剧|剧|版|故事|连续剧|漫剧|视频|内容)"
)
# 兜底：任意"数字+集"（排除"每集""第N集"）
_LOOSE = re.compile(rf"(?<!每)(?<!第)\s*({_NUM})\s*集")
# 区间："2-3集""两三集" —— 取下限更省 token
_RANGE = re.compile(rf"({_NUM})\s*[-~－—至到]\s*({_NUM})\s*集")
def cn_to_int(text: str) -> int | None:
    """中文/阿拉伯数字转整数；解析不了返回 None。
    "十"→10 "二十"→20 "三十五"→35 "两三"→2（模糊量词取下限）。
    """
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if not all(c in _CN_DIGITS or c in _CN_UNITS for c in text):
        return None
    # 纯数字串（不含十百）："二三"这种模糊量词取第一个
    if all(c in _CN_DIGITS for c in text):
        if len(text) > 1 and text[0] == "两":
            return _CN_DIGITS["两"]
        n = 0
        for c in text:
            n = n * 10 + _CN_DIGITS[c]
        return n
    total = section = num = 0
    for c in text:
        if c in _CN_DIGITS:
            num = _CN_DIGITS[c]
        else:
            unit = _CN_UNITS[c]
            section += (num if num else 1) * unit
            num = 0
    return total + section + num
def parse_episode_count(
    idea: str,
    default: int = DEFAULT_EPISODE_COUNT,
    max_count: int = MAX_EPISODE_COUNT,
) -> tuple[int, bool]:
    """解析目标集数。
    返回 (集数, 是否由用户显式指定)。
    集数被夹在 [1, max_count]；解析不出就用 default（默认 1 集）。
    """
    text = (idea or "").strip()
    if not text:
        return default, False
    # 区间优先："2-3 集"取下限 2
    m = _RANGE.search(text)
    if m:
        lo = cn_to_int(m.group(1))
        if lo:
            return max(1, min(lo, max_count)), True
    # 明确只要一集
    if _ONLY_ONE.search(text):
        return 1, True
    # 总量型表达（"共 3 集""改成三集""三集短剧"）
    m = _TOTAL.search(text)
    if m:
        n = None
        for g in m.groups():
            if g:
                n = cn_to_int(g)
                if n:
                    break
        if not n:
            n = cn_to_int(_first_num(m.group(0)))
        if n:
            return max(1, min(n, max_count)), True
    # 兜底：任意"数字+集"（已排除"每集""第N集"）
    found: list[int] = []
    for m in _LOOSE.finditer(text):
        n = cn_to_int(m.group(1))
        if n:
            found.append(n)
    if found:
        return max(1, min(max(found), max_count)), True
    return default, False
def _first_num(text: str) -> str:
    """从一段文本里取出第一个数字串。"""
    m = re.search(r"\d{1,3}|[零〇一二两三四五六七八九十百]{1,3}", text)
    return m.group(0) if m else ""
def describe_episode_spec(count: int, explicit: bool) -> str:
    """给界面/提示词用的一句话说明。"""
    if explicit:
        return f"共 {count} 集"
    return "共 1 集（你没说集数，按一集处理）"
