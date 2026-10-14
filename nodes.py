"""
ComfyUI-ScenarioExtractor
독립 세션 검수(Zero Confirmation Bias) 및 Context Loop 오버랩 규칙이 적용된 시나리오 추출기 & 프롬프트 컴파일러
"""
import os
import json
import urllib.request
import urllib.error
from typing import Tuple, Dict, Any

def _get_api_key(input_key: str) -> str:
    key = input_key.strip() if input_key else ""
    if not key:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key

def call_gemini_api(prompt: str, system_prompt: str, api_key: str, model: str = "gemini-2.5-flash") -> str:
    key = _get_api_key(api_key)
    if not key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. 노드의 api_key 필드에 입력하거나 환경변수를 설정해주세요.")

    clean_model = model.strip() if model else "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={key}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API 호출 에러 ({e.code}): {err_body}")
    except Exception as e:
        raise RuntimeError(f"Gemini 통신 실패: {str(e)}")


# =========================================================================
# 1. Scenario Writer (시나리오 작가 노드)
# =========================================================================
WRITER_SYSTEM_PROMPT = """당신은 45초 롱테이크 시네마틱 비디오(15초 3개 씬 연속 루프)를 위한 전문 시나리오 작가입니다.
사용자의 아이디어를 바탕으로 현실적이고 시각 묘사가 극도로 구체적인 3구간 45초 대본 초안을 작성하세요.

[작성 규칙]
1. 총 45초를 정확히 3개 씬으로 나눕니다:
   - 씬 1 (0초 ~ 15초): 도입 및 상황 설정, 인물의 초기 상태
   - 씬 2 (15초 ~ 30초): 상황의 진전 및 핵심 상호작용
   - 씬 3 (30초 ~ 45초): 절정 및 씬의 마무리 (엔딩 상태)
2. 각 씬마다 다음 요소를 명시하세요:
   - [인물 행동 및 표정]: 시각적으로 즉시 렌더링 가능한 구체적 물리 동작
   - [카메라 앵글 및 무빙]: 팬, 줌, 트래킹, 핸드헬드 등
   - [배경 및 조명/분위기]: 광원, 텍스처, 날씨
3. 마지막에 이전 씬과 다음 씬의 연속성을 위해 [엔딩 상태 요약 (end_state)]을 한 줄로 정리하세요.
"""

class ScenarioWriter:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "scene_idea": ("STRING", {
                    "multiline": True,
                    "default": "새벽 골목길, 네온 간판 아래에서 우산을 쓰고 누군가를 초조하게 기다리는 여성",
                    "tooltip": "시나리오의 핵심 상황, 배경, 인물에 대한 1~2줄 아이디어"
                }),
                "character_desc": ("STRING", {
                    "multiline": True,
                    "default": "20대 초반 여성, 젖은 단발머리, 오버사이즈 베이지 트렌치코트",
                    "tooltip": "주요 인물의 외형, 의상, 특징"
                }),
            },
            "optional": {
                "api_key": ("STRING", {"default": "", "tooltip": "Gemini API Key (비워두면 환경변수 GEMINI_API_KEY 사용)"}),
                "model": (["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"], {"default": "gemini-2.5-flash"}),
                "previous_end_state": ("STRING", {"default": "", "multiline": True, "tooltip": "이전 씬이 있다면 이전 씬의 종료 상태"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("draft_screenplay", "log")
    FUNCTION = "write_scenario"
    CATEGORY = "Scenario/Extractor"
    DESCRIPTION = "사용자 아이디어를 바탕으로 45초 3구간 시나리오 초안을 생성합니다."

    def write_scenario(self, scene_idea: str, character_desc: str, api_key: str = "", model: str = "gemini-2.5-flash", previous_end_state: str = ""):
        user_prompt = f"인물 정보: {character_desc}\n상황 아이디어: {scene_idea}"
        if previous_end_state:
            user_prompt += f"\n[이전 씬의 종료 상태 참조]: {previous_end_state}"

        print(f"[ScenarioWriter] ✍️ 작가 세션 호출 중 (Model: {model})...")
        draft = call_gemini_api(user_prompt, WRITER_SYSTEM_PROMPT, api_key, model)
        log = f"✓ 작가 초안 생성 완료 ({len(draft)} 자)"
        print(f"[ScenarioWriter] {log}")
        return (draft, log)


# =========================================================================
# 2. Scenario Auditor (독립 검수자 - 확증 편향 0% 스크립트 닥터)
# =========================================================================
AUDITOR_SYSTEM_PROMPT = """당신은 독립된 수석 시나리오 검수자(Script Doctor)입니다.
앞선 작가의 생성 기억이 전혀 없는 상태에서, 오직 전달된 초안 대본만을 객관적이고 엄격하게 대조 검수하세요.

[검수 및 교정 원칙 - 확증 편향 금지]
1. [언어 및 번역투 색출]:
   - '너클이 하얗게 질린다' ➔ '손마디가 하얗게 굳는다'
   - '그녀의 숨결이 공기를 가른다' 등 어색한 번역투나 과도하게 문학적인 내면 서술을 시각적이고 자연스러운 한국어로 즉시 교정하세요.
2. [비디오 생성 모델 친화적 묘사]:
   - AI 비디오 모델이 이해할 수 없는 추상적 심리 묘사는 100% 눈에 보이는 신체 움직임/시선/손동작으로 치환하세요.
3. [물리적 연속성 검증]:
   - 씬 1에서 들고 있던 우산/소품이 씬 2, 3에서 설명 없이 사라지거나 의상이 바뀌는 오류를 완벽히 통일 교정하세요.

[출력 양식]
--- 교정 내역 요약 ---
- 발견된 결함 및 교정 사항 요약 (2~3줄)

--- 최종 교정 대본 (Clean Screenplay) ---
(씬 1, 씬 2, 씬 3의 완전한 교정 대본 전문)
"""

class ScenarioAuditor:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "draft_screenplay": ("STRING", {"multiline": True, "tooltip": "작가 노드에서 출력된 시나리오 초안"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": "", "tooltip": "Gemini API Key"}),
                "model": (["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"], {"default": "gemini-2.5-flash"}),
                "custom_audit_rules": ("STRING", {"default": "", "multiline": True, "tooltip": "추가 검수 기준"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("clean_screenplay", "audit_report")
    FUNCTION = "audit_scenario"
    CATEGORY = "Scenario/Extractor"
    DESCRIPTION = "독립 백지 세션으로 작가의 대본을 검수하여 번역투와 설정 불일치를 교정합니다."

    def audit_scenario(self, draft_screenplay: str, api_key: str = "", model: str = "gemini-2.5-flash", custom_audit_rules: str = ""):
        audit_input = f"검수할 대본 초안:\n\n{draft_screenplay}"
        if custom_audit_rules:
            audit_input += f"\n\n[추가 검수 수칙]:\n{custom_audit_rules}"

        print(f"[ScenarioAuditor] 🧐 독립 검수자 세션 호출 중 (확증 편향 0% 보장)...")
        audit_res = call_gemini_api(audit_input, AUDITOR_SYSTEM_PROMPT, api_key, model)

        clean_screenplay = audit_res
        report = "검수 완료"
        if "--- 최종 교정 대본" in audit_res:
            parts = audit_res.split("--- 최종 교정 대본", 1)
            report = parts[0].strip()
            clean_screenplay = parts[1].replace("(Clean Screenplay) ---", "").strip()

        print(f"[ScenarioAuditor] ✓ 대본 검수 및 결함 교정 완료!")
        return (clean_screenplay, report)


# =========================================================================
# 3. Context Loop Compiler (오버랩 규칙 반영 프롬프트 컴파일러)
# =========================================================================
COMPILER_SYSTEM_PROMPT = """당신은 비디오 생성 AI의 Context Loop 전용 프롬프트 컴파일러입니다.
교정된 한국어 시나리오를 분석하여, 15초 단위 3개 샷(총 45초 생성 ➔ 42초 완성본)에 최적화된 영문 비디오 프롬프트를 컴파일하세요.

[⭐ 가장 중요한 Context Loop 오버랩 규칙]
- Context Loop 엔진은 씬 연결 시 [앞머리 22프레임 삭제(Trim) + 17프레임 크로스페이드(Blend)]로 인해,
  각 씬의 첫 39프레임(약 1.63초)이 이전 씬과 겹쳐지거나 잘려나갑니다!
- 따라서 프롬프트를 다음과 같이 엄격히 구성해야 합니다:
  1. Shot 1: 0초부터 정상 연출 묘사.
  2. Shot 2: 앞부분에 반드시 `Seamlessly continue the movement and posture from the previous shot.`를 명시하고, 새로운 핵심 행동은 2초 이후에 일어나도록 서술.
  3. Shot 3: 앞부분에 반드시 `Seamlessly continue the continuous motion from the previous shot.`를 명시하고, 피날레 액션은 2초 이후에 일어나도록 서술.

[출력 양식]
반드시 다음 JSON 형식으로만 응답하세요:
{
  "shot_1": "Shot 1 영문 프롬프트 (High quality cinematic description, 0-15s)",
  "shot_2": "Shot 2 영문 프롬프트 (Seamless continuation buffer in first 2s, followed by progression, 15-30s)",
  "shot_3": "Shot 3 영문 프롬프트 (Seamless continuation buffer in first 2s, followed by climax, 30-45s)"
}
"""

class ContextLoopCompiler:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "clean_screenplay": ("STRING", {"multiline": True, "tooltip": "검수 통과된 최종 대본"}),
            },
            "optional": {
                "style_prompt": ("STRING", {
                    "default": "masterpiece, cinematic lighting, 8k, photorealistic, highly detailed, film grain",
                    "multiline": True,
                    "tooltip": "공통 화풍, 조명 및 렌더링 스타일 키워드"
                }),
                "character_trigger": ("STRING", {
                    "default": "",
                    "tooltip": "캐릭터 로라 트리거 워드 (예: a woman with wet bob hair)"
                }),
                "api_key": ("STRING", {"default": "", "tooltip": "Gemini API Key"}),
                "model": (["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"], {"default": "gemini-2.5-flash"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("shot_1_prompt", "shot_2_prompt", "shot_3_prompt", "full_prompts_json")
    FUNCTION = "compile_prompts"
    CATEGORY = "Scenario/Extractor"
    DESCRIPTION = "대본을 39프레임(1.6초) 오버랩 소실 보정 규칙이 적용된 Context Loop 프롬프트 3개로 컴파일합니다."

    def compile_prompts(self, clean_screenplay: str, style_prompt: str = "", character_trigger: str = "", api_key: str = "", model: str = "gemini-2.5-flash"):
        compile_input = f"교정 대본:\n{clean_screenplay}\n\n화풍 스타일: {style_prompt}\n캐릭터 트리거: {character_trigger}"
        print(f"[ContextLoopCompiler] ⚙️ Context Loop 오버랩 규칙 적용 컴파일 중...")
        res_text = call_gemini_api(compile_input, COMPILER_SYSTEM_PROMPT, api_key, model)

        s1 = ""
        s2 = ""
        s3 = ""
        try:
            start_idx = res_text.find("{")
            end_idx = res_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = res_text[start_idx:end_idx+1]
                data = json.loads(json_str)
                s1 = data.get("shot_1", "")
                s2 = data.get("shot_2", "")
                s3 = data.get("shot_3", "")
        except Exception as e:
            print(f"[ContextLoopCompiler] JSON parse fallback: {e}")
            s1 = res_text

        def merge_style(p):
            parts = []
            if character_trigger.strip():
                parts.append(character_trigger.strip())
            if p.strip():
                parts.append(p.strip())
            if style_prompt.strip():
                parts.append(style_prompt.strip())
            return ", ".join(parts)

        final_s1 = merge_style(s1)
        final_s2 = merge_style(s2)
        final_s3 = merge_style(s3)

        full_json = json.dumps({
            "shot_1": final_s1,
            "shot_2": final_s2,
            "shot_3": final_s3
        }, ensure_ascii=False, indent=2)

        print(f"[ContextLoopCompiler] ✓ 샷 1, 2, 3 프롬프트 생성 완료 (Shot 2, 3에 1.6초 오버랩 버퍼 주입됨)")
        return (final_s1, final_s2, final_s3, full_json)


# =========================================================================
# 4. All-In-One Scenario Extractor (원클릭 올인원 노드)
# =========================================================================
class ScenarioExtractorAllInOne:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "scene_idea": ("STRING", {
                    "multiline": True,
                    "default": "새벽 골목길, 네온 간판 아래에서 우산을 쓰고 누군가를 초조하게 기다리는 여성",
                    "tooltip": "시나리오 상황 아이디어"
                }),
                "character_desc": ("STRING", {
                    "multiline": True,
                    "default": "20대 초반 여성, 젖은 단발머리, 오버사이즈 베이지 트렌치코트",
                    "tooltip": "인물 외형 묘사"
                }),
            },
            "optional": {
                "style_prompt": ("STRING", {
                    "default": "masterpiece, cinematic lighting, 8k, photorealistic, highly detailed, film grain",
                    "multiline": True
                }),
                "character_trigger": ("STRING", {"default": ""}),
                "api_key": ("STRING", {"default": "", "tooltip": "Gemini API Key"}),
                "model": (["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"], {"default": "gemini-2.5-flash"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("shot_1_prompt", "shot_2_prompt", "shot_3_prompt", "clean_screenplay", "audit_report")
    FUNCTION = "run_all"
    CATEGORY = "Scenario/Extractor"
    DESCRIPTION = "한 줄 아이디어에서 [작가 ➔ 독립 검수 ➔ Context Loop 프롬프트 분할]까지 원클릭으로 일괄 처리합니다."

    def run_all(self, scene_idea: str, character_desc: str, style_prompt: str = "", character_trigger: str = "", api_key: str = "", model: str = "gemini-2.5-flash"):
        writer = ScenarioWriter()
        auditor = ScenarioAuditor()
        compiler = ContextLoopCompiler()

        # 1. 작가
        draft, _ = writer.write_scenario(scene_idea, character_desc, api_key, model)
        # 2. 독립 검수자
        clean, report = auditor.audit_scenario(draft, api_key, model)
        # 3. 컴파일러
        s1, s2, s3, _ = compiler.compile_prompts(clean, style_prompt, character_trigger, api_key, model)

        return (s1, s2, s3, clean, report)
