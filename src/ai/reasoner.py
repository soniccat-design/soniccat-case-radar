from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

from src.models import Candidate
from src.utils.text import chinese_char_count, clamp_reason, keyword_hit


LOCAL_REASON_BANK = {
    "professional-running": [
        "中底侧墙上扬与鞋面压线形成清楚推进节奏",
        "前掌翘度和鞋腰收束关系适合拆解速度轮廓",
        "鞋面分区与厚底比例关系能强化竞速系列识别",
        "后跟稳定块和泡棉厚度关系便于开发量产沟通",
        "整鞋外侧线条连续，适合参考速度感结构表达",
    ],
    "running-outsole": [
        "橡胶分区和镂空窗口能直接参考受力布局",
        "前掌底纹方向明确，便于判断蹬伸抓地区域",
        "中足开窗与橡胶覆盖关系体现轻量化取舍",
        "外底分区边界清楚，适合拆解耐磨区域配置",
        "碳板露出位置和中足开窗能辅助判断推进层次",
    ],
    "professional-spikes": [
        "前掌钉孔排布集中，适合拆解起跑发力方向",
        "钉板边界和鞋面包覆能辅助判断锁定逻辑",
        "低帮鞋口和前掌板形共同强化专业器材属性",
        "钉孔间距清楚，便于分析前掌抓地发力节奏",
        "鞋面热贴走向能参考高速摆动中的包裹",
    ],
}


class ReasonGenerator:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        ai_config = config.get("global", {}).get("ai", {})
        env_keys = ai_config.get("default_env_keys", {})
        self.enabled = bool(ai_config.get("enabled", True))
        self.provider = os.environ.get(env_keys.get("provider", "AI_PROVIDER"), "")
        self.api_key = os.environ.get(env_keys.get("api_key", "AI_API_KEY"), "")
        self.model = os.environ.get(env_keys.get("model", "AI_MODEL"), "")
        self.base_url = os.environ.get(env_keys.get("base_url", "AI_BASE_URL"), "")
        self.timeout = int(ai_config.get("timeout_seconds", 25))
        self.vision_preferred = bool(ai_config.get("vision_preferred", True))
        reason_config = config.get("global", {}).get("reason", {})
        self.min_chars = int(reason_config.get("min_cn_chars", 20))
        self.max_chars = int(reason_config.get("max_cn_chars", 40))

    def generate(self, candidate: Candidate, category: Dict[str, Any]) -> str:
        if self.enabled and self.api_key and self.base_url and self.model:
            try:
                reason = self._generate_with_ai(candidate, category)
                if self._valid(reason):
                    return clamp_reason(reason, self.min_chars, self.max_chars)
            except Exception as exc:
                candidate.metadata["ai_error"] = str(exc)[:200]
        return self.local_reason(candidate, category)

    def local_reason(self, candidate: Candidate, category: Dict[str, Any]) -> str:
        bank = LOCAL_REASON_BANK.get(category.get("id"), LOCAL_REASON_BANK["professional-running"])
        text = " ".join([candidate.title, candidate.summary, candidate.image_url, candidate.source_url])
        if category.get("id") == "running-outsole":
            if keyword_hit(text, ["carbon", "碳板"]):
                return "碳板露出位置和中足开窗能辅助判断推进层次"
            if keyword_hit(text, ["rubber", "橡胶"]):
                return "外底橡胶覆盖边界清楚，适合拆解耐磨配置"
        if category.get("id") == "professional-spikes":
            if keyword_hit(text, ["sprint", "短跑", "起跑"]):
                return "前掌钉孔排布集中，适合拆解起跑发力方向"
        if category.get("id") == "professional-running":
            if keyword_hit(text, ["carbon", "碳板", "marathon", "马拉松"]):
                return "厚底轮廓和推进线条适合参考马拉松竞速表达"
        index = int(candidate.content_hash[:2], 16) % len(bank) if candidate.content_hash else 0
        return bank[index]

    def _generate_with_ai(self, candidate: Candidate, category: Dict[str, Any]) -> str:
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        prompt = (
            "你是专业运动鞋产品设计师。请只输出一句20至40个中文字符的参考理由，"
            "理由必须对应图片或标题中的具体设计点，不能写来源信息，不能写空泛形容词。\n"
            "分类：%s\n标题：%s\n说明：%s\n关键词：%s"
            % (
                category.get("name", category.get("id")),
                candidate.title,
                candidate.summary,
                "、".join(list(category.get("keywords_zh", []))[:5]),
            )
        )
        content: List[Dict[str, Any]]
        if self.vision_preferred and candidate.image_url:
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": candidate.image_url}},
            ]
        else:
            content = [{"type": "text", "text": prompt}]
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.4,
            "max_tokens": 80,
        }
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer %s" % self.api_key,
            },
        )
        with urlopen(request, timeout=self.timeout) as response:  # nosec - user configured endpoint
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()

    def _valid(self, reason: Optional[str]) -> bool:
        if not reason:
            return False
        count = chinese_char_count(reason)
        return self.min_chars <= count <= self.max_chars
