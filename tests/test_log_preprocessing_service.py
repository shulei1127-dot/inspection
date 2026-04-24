import json
from pathlib import Path

from app.services.log_preprocessing_service import run_log_preprocessing
from app.services.trend_enhancement_service import run_trend_enhancement


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "full_log_waf_v1" / "sample-bundle"


def test_log_preprocessing_generates_evidence_summary_and_markdown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    artifacts = run_log_preprocessing(FIXTURE_DIR)

    evidence_path = Path(artifacts.status_analysis_evidence_path)
    summary_path = Path(artifacts.status_analysis_summary_path)
    markdown_path = Path(artifacts.status_analysis_md_path)
    resource_history_csv_path = Path(artifacts.resource_history_csv_path)

    assert artifacts.run_id.startswith("prep_")
    assert evidence_path.exists()
    assert summary_path.exists()
    assert markdown_path.exists()
    assert resource_history_csv_path.exists()
    assert resource_history_csv_path.read_text(encoding="utf-8").startswith("timestamp,cpu,memory,disk")

    summary_json = summary_path.read_text(encoding="utf-8")
    markdown_text = markdown_path.read_text(encoding="utf-8")
    summary = json.loads(summary_json)

    assert '"contract_version": "status-analysis-summary/v1"' in summary_json
    assert '"restart_count_30d": 1' in summary_json
    assert '"unclean_shutdown_count_30d": 0' in summary_json
    assert summary["coverage_level"] == "full"
    assert "# SafeLine WAF 状态分析报告" in markdown_text
    assert "## 4. 状态摘要与风险线索" in markdown_text
    assert "扫描覆盖度" in markdown_text
    assert "restart=1" in markdown_text
    assert "2026-01-30 ~ 2026-04-16" not in markdown_text


def test_log_preprocessing_hands_off_to_existing_trend_chain_without_manual_markdown_edits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    preprocessing_artifacts = run_log_preprocessing(FIXTURE_DIR)
    trend_artifacts = run_trend_enhancement(Path(preprocessing_artifacts.status_analysis_md_path))

    trend_input = Path(trend_artifacts.trend_input_path).read_text(encoding="utf-8")
    trend_assessment = Path(trend_artifacts.trend_assessment_path).read_text(encoding="utf-8")

    assert '"contract_version": "trend-input/v1"' in trend_input
    assert '"contract_version": "trend-assessment/v1"' in trend_assessment
    assert '"restart_count": 1' in trend_input
    assert '"status": "pressure_high"' in trend_assessment


def test_log_preprocessing_extracts_resource_time_series_for_trend_chain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "waf-log"
    metadata_dir = source_dir / "metadata"
    resources_dir = source_dir / "resources"
    metadata_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)
    (metadata_dir / "collection_info.txt").write_text("collected_at: 2025-12-10 08:53:05 UTC\n", encoding="utf-8")
    (resources_dir / "resource_history.csv").write_text(
        "\n".join(
            [
                "timestamp,cpu,memory,disk",
                "2025-12-08 00:00:00,20%,60%,50%",
                "2025-12-08 06:00:00,24%,64%,54%",
                "2025-12-08 12:00:00,30%,70%,55%",
                "2025-12-08 18:00:00,34%,74%,59%",
                "2025-12-09 00:00:00,40%,80%,60%",
            ]
        ),
        encoding="utf-8",
    )

    preprocessing_artifacts = run_log_preprocessing(source_dir)
    summary = json.loads(Path(preprocessing_artifacts.status_analysis_summary_path).read_text(encoding="utf-8"))
    markdown_text = Path(preprocessing_artifacts.status_analysis_md_path).read_text(encoding="utf-8")
    trend_artifacts = run_trend_enhancement(Path(preprocessing_artifacts.status_analysis_md_path))
    trend_input = json.loads(Path(trend_artifacts.trend_input_path).read_text(encoding="utf-8"))
    trend_assessment = json.loads(Path(trend_artifacts.trend_assessment_path).read_text(encoding="utf-8"))

    assert len(summary["resource_time_series"]) == 3
    assert summary["resource_time_series"][0]["source_ref"] == "resources/resource_history.csv"
    assert summary["resource_time_series"][0]["aggregation"] == "12h_average"
    assert summary["resource_time_series"][0]["sample_count"] == 1
    assert summary["resource_time_series"][0]["cpu_percent"] == 22.0
    assert summary["resource_time_series"][0]["memory_percent"] == 62.0
    assert summary["resource_time_series"][0]["disk_percent"] == 52.0
    assert Path(preprocessing_artifacts.resource_history_csv_path).read_text(encoding="utf-8").splitlines() == [
        "timestamp,cpu,memory,disk",
        "2025-12-08T00:00:00Z,22.0,62.0,52.0",
        "2025-12-08T12:00:00Z,32.0,72.0,57.0",
        "2025-12-09T00:00:00Z,40.0,80.0,60.0",
    ]
    assert "### 1.5 资源历史样本" in markdown_text
    assert "| 2025-12-08 00:00:00 | 22.0% | 62.0% | 52.0% | 1 | resources/resource_history.csv |" in markdown_text
    assert len(trend_input["metrics"]["cpu"]["samples"]) >= 3
    assert len(trend_input["metrics"]["memory"]["samples"]) >= 3
    assert len(trend_input["metrics"]["disk"]["samples"]) >= 3
    assert trend_assessment["metrics"]["memory"]["status"] in {"deteriorating", "pressure_high"}


def test_log_preprocessing_supports_minion_collect_directory_name_and_top_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "minion-command-collect-CT0101202309048DA0-chaitin_safeline-1765356785"
    system_dir = source_dir / "system"
    system_dir.mkdir(parents=True)
    (system_dir / "top.txt").write_text(
        "\n".join(
            [
                "top - 16:53:14 up 347 days, 23:25,  1 user,  load average: 3.47, 3.28, 3.32",
                "%Cpu(s): 19.9 us,  0.3 sy,  0.0 ni, 79.7 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st",
                "MiB Mem :  30791.5 total,    323.5 free,  26161.1 used,   4306.9 buff/cache",
            ]
        ),
        encoding="utf-8",
    )

    artifacts = run_log_preprocessing(source_dir)
    summary = json.loads(Path(artifacts.status_analysis_summary_path).read_text(encoding="utf-8"))

    assert summary["metadata"]["collect_time"] == "2025-12-10T08:53:05Z"
    assert summary["metadata"]["window_start"] == "2025-11-10T08:53:05Z"
    assert summary["cpu_snapshot"]["current_value"] == 20.2
    assert summary["memory_snapshot"]["current_value"] == 85.0
    assert summary["uptime_snapshot"]["current_value"] == 30065100.0
    assert Path(artifacts.resource_history_csv_path).read_text(encoding="utf-8").splitlines() == [
        "timestamp,cpu,memory,disk",
        "2025-12-10T00:00:00Z,20.2,85.0,",
    ]


def test_log_preprocessing_generates_header_only_resource_history_without_reliable_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "waf-log"
    system_dir = source_dir / "system"
    system_dir.mkdir(parents=True)
    (system_dir / "current-boot.log").write_text(
        "2025-12-10 10:00:00 health check completed without resource metrics\n",
        encoding="utf-8",
    )

    artifacts = run_log_preprocessing(source_dir)
    summary = json.loads(Path(artifacts.status_analysis_summary_path).read_text(encoding="utf-8"))

    assert Path(artifacts.resource_history_csv_path).read_text(encoding="utf-8") == "timestamp,cpu,memory,disk\n"
    assert summary["resource_time_series"] == []


def test_log_preprocessing_selective_mode_skips_full_source_copy_and_records_coverage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "minion-command-collect-CT0101202309048DA0-chaitin_safeline-1765356785"
    system_dir = source_dir / "system"
    detector_dir = source_dir / "safeline" / "logs" / "detector"
    system_dir.mkdir(parents=True)
    detector_dir.mkdir(parents=True)
    (system_dir / "top.txt").write_text(
        "\n".join(
            [
                "top - 16:53:14 up 1 days, 01:00,  1 user,  load average: 0.1, 0.1, 0.1",
                "%Cpu(s): 10.0 us,  1.0 sy,  0.0 ni, 89.0 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st",
                "MiB Mem :  100.0 total,    10.0 free,  80.0 used,   10.0 buff/cache",
            ]
        ),
        encoding="utf-8",
    )
    (detector_dir / "snserver.log").write_text("x" * 128, encoding="utf-8")

    artifacts = run_log_preprocessing(source_dir, large_file_bytes=10)
    workdir = Path(artifacts.status_analysis_md_path).parent
    evidence = json.loads(Path(artifacts.status_analysis_evidence_path).read_text(encoding="utf-8"))
    summary = json.loads(Path(artifacts.status_analysis_summary_path).read_text(encoding="utf-8"))

    assert not (workdir / "source_logs").exists()
    assert evidence["scan_coverage"]["mode"] == "selective"
    assert evidence["scan_coverage"]["copied_source"] is False
    assert evidence["scan_coverage"]["coverage_level"] == "partial"
    assert "safeline/logs/detector/snserver.log" in summary["major_skipped_sources"]
    assert summary["coverage_level"] == "partial"
    assert summary["scan_limitations"]
    assert summary["coverage_warnings"]


def test_log_preprocessing_full_copy_debug_mode_still_keeps_source_logs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    artifacts = run_log_preprocessing(FIXTURE_DIR, copy_source=True)
    workdir = Path(artifacts.status_analysis_md_path).parent
    evidence = json.loads(Path(artifacts.status_analysis_evidence_path).read_text(encoding="utf-8"))

    assert (workdir / "source_logs").exists()
    assert artifacts.source_directory_path.endswith("/source_logs")
    assert evidence["scan_coverage"]["mode"] == "full_copy"
    assert evidence["scan_coverage"]["copied_source"] is True


def test_log_preprocessing_aggregates_repeated_service_findings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "waf-log"
    metadata_dir = source_dir / "metadata"
    container_dir = source_dir / "container"
    metadata_dir.mkdir(parents=True)
    container_dir.mkdir(parents=True)
    (metadata_dir / "collection_info.txt").write_text("collected_at: 2025-12-10 08:53:05 UTC\n", encoding="utf-8")
    (container_dir / "mgt-es.log").write_text(
        "\n".join(
            [
                "2025-12-08T03:22:35.155440283Z Failed to execute [SearchRequest{index=detect_log}]",
                "2025-12-08T03:22:35.155462593Z Caused by: org.elasticsearch.search.query.QueryPhaseExecutionException: Query Failed [Failed to execute main query]",
                "2025-12-08T03:23:27.092132757Z Failed to execute [SearchRequest{index=detect_log}]",
                "2025-12-08T03:23:27.092183727Z Caused by: org.elasticsearch.search.query.QueryPhaseExecutionException: Query Failed [Failed to execute main query]",
            ]
        ),
        encoding="utf-8",
    )

    artifacts = run_log_preprocessing(source_dir)
    evidence = json.loads(Path(artifacts.status_analysis_evidence_path).read_text(encoding="utf-8"))
    summary = json.loads(Path(artifacts.status_analysis_summary_path).read_text(encoding="utf-8"))

    assert len(evidence["key_findings"]) == 4
    assert len(summary["service_findings"]) == 1
    assert "事件链" in summary["service_findings"][0]["summary"]
    assert "已合并 4 条相关证据摘录" in summary["service_findings"][0]["summary"]
    assert "QueryPhaseExecutionException" in summary["service_findings"][0]["summary"]


def test_log_preprocessing_keeps_unrelated_service_findings_separate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "waf-log"
    metadata_dir = source_dir / "metadata"
    container_dir = source_dir / "container"
    metadata_dir.mkdir(parents=True)
    container_dir.mkdir(parents=True)
    (metadata_dir / "collection_info.txt").write_text("collected_at: 2025-12-10 08:53:05 UTC\n", encoding="utf-8")
    (container_dir / "mgt-es.log").write_text(
        "2025-12-08T03:22:35.155440283Z Failed to execute [SearchRequest{index=detect_log}]\n",
        encoding="utf-8",
    )
    (container_dir / "mgt-api.log").write_text(
        "2025-12-08T04:22:35.155440283Z unhealthy response from management api\n",
        encoding="utf-8",
    )

    artifacts = run_log_preprocessing(source_dir)
    summary = json.loads(Path(artifacts.status_analysis_summary_path).read_text(encoding="utf-8"))

    assert len(summary["service_findings"]) == 2
    assert {finding["component"] for finding in summary["service_findings"]} == {"mgt-es", "mgt-api"}


def test_log_preprocessing_extracts_disk_from_low_ambiguity_df_like_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "waf-log"
    system_dir = source_dir / "system"
    system_dir.mkdir(parents=True)
    (system_dir / "disk.txt").write_text(
        "\n".join(
            [
                "Filesystem      Size  Used Avail Use% Mounted on",
                "/dev/sda2       100G   76G   24G  76% /",
                "tmpfs            10G     0   10G   0% /run",
            ]
        ),
        encoding="utf-8",
    )

    artifacts = run_log_preprocessing(source_dir)
    summary = json.loads(Path(artifacts.status_analysis_summary_path).read_text(encoding="utf-8"))

    assert summary["disk_snapshot"]["current_value"] == 76.0
    assert summary["disk_snapshot"]["source_ref"] == "system/disk.txt"


def test_log_preprocessing_keeps_disk_unknown_without_supported_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "waf-log"
    system_dir = source_dir / "system"
    system_dir.mkdir(parents=True)
    (system_dir / "current-boot.log").write_text(
        'Dec 10 16:00:08 host hwminion[1177]: time="2025-12-10T16:00:08+08:00" level=info msg="use 2 milliseconds" job=UpdateDiskInfo\n',
        encoding="utf-8",
    )

    artifacts = run_log_preprocessing(source_dir)
    summary = json.loads(Path(artifacts.status_analysis_summary_path).read_text(encoding="utf-8"))

    assert summary["disk_snapshot"] is None
    assert "未从约定优先级来源中提取到磁盘当前快照。" in summary["warnings"]
