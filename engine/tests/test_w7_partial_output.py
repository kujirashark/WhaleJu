"""模型输出被截断时的降级处理。
场景：厂商关流 / max_tokens 触顶 / 限流中断，模型只吐了半截 JSON。
旧版整份丢弃并报"无法解析为剧本"，用户白跑一轮，还被错误提示
"到设置里检查文本模型"（模型配置明明是好的）。
新版要求：
- 能救回已写完的那几集就救回，并标记 partial
- 连一集都救不回时，错误要说清是"没写完"，并带上原始输出片段
- 错误码与提示不能误导用户去改模型配置
"""
from __future__ import annotations
import json
import pytest
from engine.app.workflow.content import ContentGenerator, NoProviderError
def _gen() -> ContentGenerator:
    """只要解析能力，不需要真实数据库。"""
    return ContentGenerator.__new__(ContentGenerator)
# 一集完整 + 第二集写到一半被截断
TRUNCATED_SCRIPT = (
    '{"title":"被截断的剧","episodes":['
    '{"idx":1,"title":"第一集：开场","tags":["标签A"],"script":"第一集的完整正文，写完了。"},'
    '{"idx":2,"title":"第二集：中断","tags":["标签B"],"script":"第二集正写到一半就断'
)
def test_truncated_output_saves_completed_episodes():
    """截断时必须保住已写完的那一集，而不是全盘丢弃。"""
    data, partial = _gen()._parse_json_lenient(TRUNCATED_SCRIPT)
    assert partial is True
    assert data["title"] == "被截断的剧"
    assert len(data["episodes"]) == 2
    assert data["episodes"][0]["script"] == "第一集的完整正文，写完了。"
    assert data["episodes"][0]["tags"] == ["标签A"]
    # 正在写的那一集也要保住已写出的部分
    assert data["episodes"][1]["script"] == "第二集正写到一半就断"
    assert data["episodes"][1]["title"] == "第二集：中断"
def test_complete_output_is_not_marked_partial():
    """完整输出不该被当成残缺。"""
    raw = json.dumps({
        "title": "完整的剧",
        "episodes": [{"idx": 1, "title": "第一集", "tags": [], "script": "正文"}],
    }, ensure_ascii=False)
    data, partial = _gen()._parse_json_lenient(raw)
    assert partial is False
    assert data["title"] == "完整的剧"
def test_garbage_output_raises_with_diagnosable_message():
    """完全救不回来时：错误要说清"没写完"并带上原始片段，错误码 E4004。"""
    with pytest.raises(NoProviderError) as exc:
        _gen()._parse_json_lenient("模型只说了句『我来写剧本了』然后就没了")
    assert exc.value.code == "E4004"
    assert "没写完" in str(exc.value)
    # 原始片段要带上，否则用户和开发者都无从判断发生了什么
    assert "我来写剧本了" in str(exc.value)
def test_truncated_shots_are_recovered():
    """镜头表截断时也要保住已写完的镜头。"""
    raw = (
        '{"shots":['
        '{"idx":1,"scene":"第一个镜头","importance":"key"},'
        '{"idx":2,"scene":"第二个镜头写到一半'
    )
    data, partial = _gen()._parse_json_lenient(raw, kind="shots")
    assert partial is True
    assert len(data["shots"]) == 2
    assert data["shots"][0] == {"idx": 1, "scene": "第一个镜头", "importance": "key"}
    assert data["shots"][1]["scene"] == "第二个镜头写到一半"
def test_markdown_fenced_json_still_works():
    """模型用 ```json 包裹时仍要能正常解析。"""
    raw = '```json\n{"title":"带围栏的剧","episodes":[{"idx":1,"title":"T","script":"S"}]}\n```'
    data, partial = _gen()._parse_json_lenient(raw)
    assert partial is False
    assert data["title"] == "带围栏的剧"
def test_escaped_quotes_inside_script_survive_recovery():
    """正文里的引号（\\"）不能把提取逻辑搞乱。"""
    raw = (
        '{"title":"引号剧","episodes":['
        '{"idx":1,"title":"第一集","script":"他说\\"这是真的\\"，然后走了。"}'
    )
    data, partial = _gen()._parse_json_lenient(raw)
    assert partial is True  # 缺尾括号，算残缺
    assert data["episodes"][0]["script"] == '他说"这是真的"，然后走了。'
