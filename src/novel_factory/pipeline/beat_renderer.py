"""
Beat Renderer - 节拍渲染生成器 (ACL 2023 DOC 契约执行)
将 Codex 上下文、微事件密度清单、镜头机位要求与动态禁令词精确编译为 Writer Agent 执行指令。
"""

from typing import Any, Dict, List, Optional
from src.novel_factory.codex.codex_assembler import AssembledContext
from src.novel_factory.schemas.beat import BeatContract, BeatOutput, CameraAngle


class BeatRenderer:
    """DOC 节拍 Prompt 编译器与输出解析器"""

    def compile_writer_prompt(
        self,
        assembled_context: AssembledContext,
        scene_beat: BeatContract,
        dynamic_ban_list: Optional[List[str]] = None,
        style_notes: Optional[str] = None,
        governance_directives: Optional[List[str]] = None,
        persona_block: str = "",
        time_anchor_line: str = ""
    ) -> Dict[str, str]:
        """
        编译系统 Prompt 与用户任务 Prompt
        """
        # 1. 镜头机位指导
        camera_guides = []
        for cam in scene_beat.required_camera_angles:
            if cam == CameraAngle.POV:
                camera_guides.append("- 【第一/第三人称主视点】关注角色即时生理感觉（心跳、手心温度、呼吸）")
            elif cam == CameraAngle.CLOSE_UP:
                camera_guides.append("- 【微距特写机位】具体物件物理细节（伤口渗血、剑锋冷芒、瞳孔微颤）")
            elif cam == CameraAngle.PANORAMIC:
                camera_guides.append("- 【全景环境机位】光影、天色、气温、周遭压抑氛围")
            elif cam == CameraAngle.REACTION_CAM:
                camera_guides.append("- 【围观震惊反应机位】第三方旁观者的具体失态动作（如手中杯盏捏碎、后退失语）")

        # 2. 微事件密度清单 (Anti-Drooling & Zero-Water)
        event_lines = []
        for ev in scene_beat.micro_events:
            event_lines.append(f"- [必须推进事件]: {ev.description}")

        # 3. 动态禁令与黑名单
        prohibitions = list(scene_beat.strict_prohibitions)
        if dynamic_ban_list:
            prohibitions.append(f"跨章高频疲劳词动态禁令: 严禁出现 {', '.join(dynamic_ban_list[:10])}")

        # 4. 长程治理指令（伏笔回收/爽点调度/支线续更/人设声纹/时间锚点）
        gov_parts: List[str] = []
        if time_anchor_line:
            gov_parts.append(time_anchor_line)
        if persona_block:
            gov_parts.append(persona_block)
        if governance_directives:
            gov_parts.append("【本章长程治理强制指令】")
            gov_parts.extend(f"- {d}" for d in governance_directives)
        governance_block = ("\n" + "\n".join(gov_parts) + "\n") if gov_parts else ""

        system_prompt = f"""你是一名顶级商业小说主笔作家。你必须严格依据给定的分镜契约渲染正文。

【硬性生产准则】:
1. 【Show, Don't Tell】: 严禁以作者上帝视角进行任何说教或哲学升华总结，严禁出现‘这让他深刻明白/意识到...’等说明文总结句；
2. 【移动端段落律动】: 单段严禁超过 3 句话，多用利落短句，关键动作与情绪反转独占单行；
3. 【微事件密度约束】: 必须严格推进指定的全部微事件，事件写完即收笔，严禁为了凑字数而空洞注水；
4. 【镜头机位履约】: 必须清晰呈现契约要求的各个镜头机位。"""

        user_prompt = f"""【当前任务上下文 (Codex Compilation)】:
{assembled_context.raw_full_context}

【本节拍分镜契约 (Beat Contract)】:
- 节拍编号: {scene_beat.beat_id} (第 {scene_beat.chapter_index} 章第 {scene_beat.beat_index} 拍)
- 叙事节奏: {scene_beat.pacing_type.value}
- 目标字数区间: 约 {scene_beat.target_words} 字
- 场景氛围: {scene_beat.scene_atmosphere or '默认当前环境'}

【必须覆盖的镜头机位】:
{chr(10).join(camera_guides)}

【微事件密度清单 (推进完成即收尾)】:
{chr(10).join(event_lines) if event_lines else '- 按照前置/后置条件平稳推进主线'}

【前置条件依赖】:
{chr(10).join([f'- {p}' for p in scene_beat.pre_conditions])}

【执行后必须达成的后置契约】:
{chr(10).join([f'- {p}' for p in scene_beat.post_conditions])}

【严格禁令事项】:
{chr(10).join([f'- {p}' for p in prohibitions]) if prohibitions else '- 无特殊禁令'}

{governance_block}
请直接输出符合上述所有契约的正文段落，不要包含任何前言、开场白或后记。"""

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt
        }

    def parse_output(self, beat_id: str, raw_llm_response: str) -> BeatOutput:
        """解析模型输出并封装为结构化节拍对象"""
        clean_prose = raw_llm_response.strip()
        word_count = len(clean_prose)

        return BeatOutput(
            beat_id=beat_id,
            prose=clean_prose,
            actual_words=word_count,
            qc_passed=False
        )
