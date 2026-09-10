"""验证 agent_utils.demo_output 的演示 JSON 能通过各站契约校验。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from studios import agent_utils as au
from schemas.script import Script
from schemas.visual_bible import VisualBible
from schemas.shot_list import ShotList
from schemas.prompt_list import PromptList
from schemas.editing_blueprint import EditingBlueprint
from schemas.qc_report import QcReport

# 构造各站 user_prompt（与 run.py 拼接方式一致）
script_json = au.demo_output("writer", au.demo_output("producer", "雨夜便利店的神秘顾客"))
script = Script.model_validate(au.safe_parse_json(script_json))
mp = au.safe_parse_json(au.demo_output("producer", "雨夜便利店的神秘顾客"))

director_in = json.dumps({"script": json.loads(script_json)}, ensure_ascii=False)
shot_list_json = au.demo_output("director", director_in)
sl = ShotList.model_validate(au.safe_parse_json(shot_list_json))
assert len(sl.shots) == 4 * 3, f"demo director 应产出 12 镜, got {len(sl.shots)}"

art_in = json.dumps({"script": json.loads(script_json)}, ensure_ascii=False)
vb = VisualBible.model_validate(au.safe_parse_json(au.demo_output("art_director", art_in)))

cam = au.safe_parse_json(au.demo_output("cinematographer", shot_list_json))
assert isinstance(cam, dict) and len(cam) == len(sl.shots), "cinematographer 输出应按 shot_id 索引"
perf = au.safe_parse_json(au.demo_output("actor", shot_list_json))
assert isinstance(perf, dict) and len(perf) == len(sl.shots)

prompter_in = json.dumps({"shot_list": json.loads(shot_list_json), "visual_bible": json.loads(au.demo_output("art_director", art_in))}, ensure_ascii=False)
pl = PromptList.model_validate(au.safe_parse_json(au.demo_output("prompter", prompter_in)))
assert len(pl.prompts) == len(sl.shots)

editor_in = json.dumps({"shot_list": json.loads(shot_list_json)}, ensure_ascii=False)
eb = EditingBlueprint.model_validate(au.safe_parse_json(au.demo_output("editor", editor_in)))
assert len(eb.timeline) == len(sl.shots)
assert eb.total_frames == eb.timeline[-1].end_frame + 1  # 闭区间：总帧数 = 末镜出点 + 1

critic_in = json.dumps({"stage": "script", "artifact": json.loads(script_json)}, ensure_ascii=False)
qr = QcReport.model_validate(au.safe_parse_json(au.demo_output("critic", critic_in)))
assert qr.passed is True and qr.stage == "script"

# AgentCaller demo 模式非空
caller = au.AgentCaller(demo_mode=True)
assert caller.call("producer", "producer", "雨夜便利店的神秘顾客")
assert caller.cost_usd() == 0.0

# safe_parse_json 边界
assert au.safe_parse_json('```json\n{"a": 1}\n```') == {"a": 1}
assert au.safe_parse_json('说明文字 {"b": [1,2]} 尾巴') == {"b": [1, 2]}
try:
    au.safe_parse_json("不是 JSON")
    raise SystemExit("应抛 JSONParseError")
except au.JSONParseError as exc:
    assert "原文前 200 字" in str(exc)

print("OK: demo 输出全部通过契约校验；safe_parse_json 边界正常")
