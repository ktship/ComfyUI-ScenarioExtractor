"""
ComfyUI-ScenarioExtractor
독립 검수(Zero Bias) & Context Loop 오버랩 규칙이 적용된 시나리오 추출기 커스텀 노드 패키지
"""
from .nodes import (
    ScenarioWriter,
    ScenarioAuditor,
    ContextLoopCompiler,
    ScenarioExtractorAllInOne,
)

NODE_CLASS_MAPPINGS = {
    "ScenarioWriter": ScenarioWriter,
    "ScenarioAuditor": ScenarioAuditor,
    "ContextLoopCompiler": ContextLoopCompiler,
    "ScenarioExtractorAllInOne": ScenarioExtractorAllInOne,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ScenarioWriter": "✍️ 시나리오 작가 (Scenario Writer)",
    "ScenarioAuditor": "🧐 독립 검수자 (Scenario Auditor - Zero Bias)",
    "ContextLoopCompiler": "⚙️ Context Loop 프롬프트 컴파일러 (42s Overlap Engine)",
    "ScenarioExtractorAllInOne": "🎬 시나리오 추출기 올인원 (All-In-One Extractor)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
