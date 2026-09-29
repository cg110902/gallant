"""
声明式配置生效性测试

配置项如果代码不读取，就只是装饰品。本测试确保 project.yaml 里新增的
contract_audit / governance / runtime 配置段真正驱动运行时行为。
"""

from pathlib import Path

import pytest
import yaml

from src.novel_factory.orchestrator import NovelFactoryOrchestrator


def _write_project(tmp_path: Path, overrides: dict) -> str:
    base = {
        "project_name": "TEST_BOOK",
        "project_title": "测试作品",
        "version": "1.0.0",
    }
    base.update(overrides)
    p = tmp_path / "project.yaml"
    p.write_text(yaml.safe_dump(base, allow_unicode=True), encoding="utf-8")
    return str(p)


def test_contract_audit_config_is_applied(tmp_path: Path):
    cfg = _write_project(tmp_path, {
        "contract_audit": {
            "enforce_word_count": False,
            "enforce_camera_coverage": False,
            "min_camera_coverage_ratio": 0.9,
            "micro_event_high_confidence": 0.8,
            "micro_event_low_confidence": 0.1,
        }
    })
    orch = NovelFactoryOrchestrator(project_config_path=cfg, db_path=":memory:")
    a = orch.contract_auditor
    assert a.enforce_word_count is False
    assert a.enforce_camera_coverage is False
    assert a.min_camera_coverage_ratio == 0.9
    assert a.high_confidence == 0.8
    assert a.low_confidence == 0.1
    orch.close()


def test_governance_config_is_applied(tmp_path: Path):
    cfg = _write_project(tmp_path, {
        "governance": {
            "enforce": False,
            "strict_unregistered_entities": False,
            "max_simhash_incidents_per_chapter": 3,
            "foreshadow_due_soon_window": 25,
            "hook_min_acceptable_score": 7.5,
        }
    })
    orch = NovelFactoryOrchestrator(project_config_path=cfg, db_path=":memory:")
    assert orch.enforce_governance is False
    assert orch.strict_unregistered_entities is False
    assert orch.max_simhash_incidents_per_chapter == 3
    assert orch.foreshadow_due_soon_window == 25
    assert orch.hook_enforcer.min_acceptable_score == 7.5
    orch.close()


def test_defaults_are_strict_when_config_absent(tmp_path: Path):
    """没有配置时必须默认从严，而不是默认放行"""
    cfg = _write_project(tmp_path, {})
    orch = NovelFactoryOrchestrator(project_config_path=cfg, db_path=":memory:")
    assert orch.enforce_governance is True
    assert orch.strict_unregistered_entities is True
    assert orch.max_simhash_incidents_per_chapter == 0
    assert orch.contract_auditor.enforce_word_count is True
    orch.close()


def test_shipped_project_yaml_is_loadable_and_wired():
    """仓库自带的 project.yaml 必须可被加载且配置项真实生效"""
    root = Path(__file__).resolve().parent.parent
    proj = root / "project.yaml"
    assert proj.exists()

    raw = yaml.safe_load(proj.read_text(encoding="utf-8"))
    orch = NovelFactoryOrchestrator(project_config_path=str(proj), db_path=":memory:")
    assert orch.enforce_governance == raw["governance"]["enforce"]
    assert orch.hook_enforcer.min_acceptable_score == raw["governance"]["hook_min_acceptable_score"]
    assert orch.contract_auditor.high_confidence == raw["contract_audit"]["micro_event_high_confidence"]
    orch.close()


def test_compliance_pack_path_is_honored(tmp_path: Path):
    pack = tmp_path / "my_compliance.yaml"
    pack.write_text(yaml.safe_dump({
        "categories": [{"name": "CUSTOM", "action": "BLOCK", "terms": ["自定义违禁词"]}]
    }, allow_unicode=True), encoding="utf-8")

    cfg = _write_project(tmp_path, {"qc_pipeline": {"compliance_pack": str(pack)}})
    orch = NovelFactoryOrchestrator(project_config_path=cfg, db_path=":memory:")
    assert "CUSTOM" in orch.compliance_scanner.categories
    assert orch.compliance_scanner.scan("这里有自定义违禁词").passed is False
    orch.close()


def test_all_shipped_configs_parse():
    """所有随仓库分发的 YAML 配置必须可解析（防止 project.yaml 引用到不存在的文件）"""
    root = Path(__file__).resolve().parent.parent
    for path in sorted((root / "configs").rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data is not None, f"{path} 解析为空"

    raw = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
    for key in ("genre", "pacing"):
        ref = raw.get(key, {}).get("config_path")
        if ref:
            assert (root / ref).exists(), f"project.yaml 引用了不存在的配置: {ref}"
    for ref in raw.get("qc_pipeline", {}).get("rule_packs", []):
        assert (root / ref).exists(), f"规则包不存在: {ref}"


def test_alternate_pacing_config_exists_and_parses():
    """project.yaml 注释中承诺的 classic_three_act 必须真实存在"""
    root = Path(__file__).resolve().parent.parent
    p = root / "configs" / "pacing" / "classic_three_act.yaml"
    assert p.exists()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["pacing_id"] == "CLASSIC_THREE_ACT"
    assert len(data["acts"]) == 3


def test_subagent_definitions_exist():
    """AGENTS.md 声明的三个 subagent 必须有真实定义文件"""
    root = Path(__file__).resolve().parent.parent
    for name in ("novel_director", "novel_writer", "novel_judge"):
        f = root / ".agent" / "subagents" / f"{name}.md"
        assert f.exists(), f"缺少 subagent 定义: {name}"
        content = f.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert f"name: {name}" in content


def test_hitl_config_is_applied(tmp_path: Path):
    cfg = _write_project(tmp_path, {
        "hitl": {
            "enable": False,
            "patch_exhaustion_threshold": 7,
            "state_file": str(tmp_path / "custom_hitl.json"),
        }
    })
    orch = NovelFactoryOrchestrator(project_config_path=cfg, db_path=":memory:")
    assert orch.enable_hitl is False
    assert orch.hitl_patch_exhaustion_threshold == 7
    assert orch.hitl_manager.state_file == tmp_path / "custom_hitl.json"
    orch.close()


def test_llm_gateway_config_is_applied(tmp_path: Path):
    from src.novel_factory.llm.client import MockLLMProvider

    cfg = _write_project(tmp_path, {
        "llm_gateway": {
            "max_retries": 9, "retry_base_delay": 0.25,
            "circuit_failure_threshold": 2, "circuit_recovery_timeout": 5.0,
        }
    })
    orch = NovelFactoryOrchestrator(
        project_config_path=cfg, db_path=":memory:", llm_provider=MockLLMProvider()
    )
    gw = orch.llm_gateway
    assert gw is not None
    assert gw.config.max_retries == 9
    assert gw.config.retry_base_delay == 0.25
    assert gw.config.circuit_failure_threshold == 2
    orch.close()


def test_no_gateway_when_using_plain_callable(tmp_path: Path):
    """纯 callable 模式下不应凭空造出网关"""
    cfg = _write_project(tmp_path, {})
    orch = NovelFactoryOrchestrator(
        project_config_path=cfg, db_path=":memory:", llm_worker=lambda s, u: "x"
    )
    assert orch.llm_gateway is None
    orch.close()


def test_shipped_project_yaml_declares_new_sections():
    root = Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
    for key in ("contract_audit", "governance", "runtime", "llm_gateway", "hitl", "outline"):
        assert key in raw, f"project.yaml 缺少 {key} 配置段"
