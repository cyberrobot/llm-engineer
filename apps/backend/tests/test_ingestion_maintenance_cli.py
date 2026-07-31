import json

from assistant.maintenance import ingestion
from assistant.maintenance.ingestion import MaintenanceCategory, MaintenanceResult


class FakeService:
    calls: list[tuple[object, bool]] = []

    def run(self, category, *, dry_run):
        self.calls.append((category, dry_run))
        return MaintenanceResult(category, dry_run=dry_run, lock_acquired=True)

    def run_all(self, *, dry_run):
        self.calls.append(("run-all", dry_run))
        return [
            MaintenanceResult(
                MaintenanceCategory.expired_lease_recovery,
                dry_run=dry_run,
                lock_acquired=True,
            )
        ]


def test_cli_defaults_destructive_command_to_dry_run(monkeypatch, capsys):
    fake = FakeService()
    fake.calls = []
    monkeypatch.setattr(ingestion, "build_service", lambda: fake)

    exit_code = ingestion.main(["cleanup-jobs", "--json"])

    assert exit_code == 0
    assert fake.calls == [(MaintenanceCategory.terminal_job_retention, True)]
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_cli_requires_explicit_execute_flag_to_mutate(monkeypatch):
    fake = FakeService()
    fake.calls = []
    monkeypatch.setattr(ingestion, "build_service", lambda: fake)

    assert ingestion.main(["reconcile-stale-jobs", "--execute"]) == 0
    assert fake.calls == [(MaintenanceCategory.expired_lease_recovery, False)]


def test_cleanup_orphans_reports_representation_boundary_and_chunk_integrity(monkeypatch):
    fake = FakeService()
    fake.calls = []
    monkeypatch.setattr(ingestion, "build_service", lambda: fake)

    assert ingestion.main(["cleanup-orphans", "--execute"]) == 0
    assert fake.calls == [
        (MaintenanceCategory.orphan_representation_cleanup, False),
        (MaintenanceCategory.orphan_chunk_cleanup, False),
    ]


def test_cli_exposes_every_narrow_command_and_run_all():
    parser = ingestion.build_parser()
    help_text = parser.format_help()

    for command in (
        "report",
        "cleanup-jobs",
        "cleanup-step-history",
        "cleanup-superseded-representations",
        "cleanup-orphans",
        "cleanup-temp-sources",
        "reconcile-stale-jobs",
        "repair-committed-jobs",
        "run-all",
    ):
        assert command in help_text
