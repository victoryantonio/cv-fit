"""Composition root. Manual constructor injection; no DI framework."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import create_db_engine, create_session_factory
from app.llm_probe import ProviderProbe
from app.llm_steps import Steps, build_steps
from app.modules.analysis.constraints import UserConstraints
from app.modules.analysis.cover import CoverWriter
from app.modules.analysis.openai_client import OpenAiLLMClient
from app.modules.analysis.pipeline import Pipeline
from app.modules.analysis.ports import LLMClient
from app.modules.analysis.service import AnalysisService
from app.modules.analysis.steps import JdStructurer, Matcher
from app.modules.analysis.suggest import Suggester
from app.modules.analysis.tasks import TaskService
from app.modules.analysis.worker import Worker
from app.modules.cvs.parser import DocumentParser
from app.modules.cvs.parser_runner import SubprocessParser
from app.modules.cvs.service import CvService
from app.modules.jobs.mcp_source import McpJobAlertSource
from app.modules.jobs.ports import JobAlertSource
from app.modules.jobs.prefilter import PrefilterCriteria
from app.modules.jobs.service import JobService
from app.modules.platform.data_controls import DataControlsService
from app.modules.platform.health import HealthService, LLMProbe
from app.modules.platform.settings_service import SettingsService
from app.shared.clock import Clock, SystemClock
from app.shared.http import SafeFetcher
from app.shared.secrets import KeyringSecretStore, SecretStore

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    clock: Clock
    secret_store: SecretStore
    http: SafeFetcher
    health: HealthService
    settings_service: SettingsService
    data_controls: DataControlsService
    cvs: CvService
    jobs: JobService
    llm: LLMClient
    jd_structurer: JdStructurer
    matcher: Matcher
    suggester: Suggester
    cover_writer: CoverWriter
    analysis: AnalysisService
    tasks: TaskService
    worker: Worker


@dataclass(frozen=True, slots=True)
class _Infra:
    """Everything that exists before a module does: config, engine, clock, secrets."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    clock: Clock
    secret_store: SecretStore
    settings_service: SettingsService


_Steps = Steps


def _constraints(settings_service: SettingsService) -> UserConstraints:
    """Hand the analysis module a snapshot instead of letting it read platform."""
    payload = settings_service.read()["non_negotiables"]
    floor = payload.get("salary_floor") or None
    return UserConstraints(
        languages=tuple(payload.get("languages") or ()),
        locations=tuple(payload.get("locations") or ()),
        work_modes=tuple(payload.get("work_modes") or ()),
        salary_floor_amount=float(floor["amount"]) if floor else None,
        salary_floor_currency=floor.get("currency") if floor else None,
        work_authorization=payload.get("work_authorization"),
    )


def _alert_source(settings: Settings) -> JobAlertSource | None:
    """No client secret means no helper: sync then reports GMAIL_NOT_CONNECTED."""
    if settings.gmail_client_secret_path is None:
        return None
    return McpJobAlertSource(
        command=settings.gmail_mcp_command,
        extra_env={
            "PYTHONPATH": str(BACKEND_ROOT),
            "GMAIL_CLIENT_SECRET_PATH": str(settings.gmail_client_secret_path),
        },
    )


def _criteria(settings_service: SettingsService) -> PrefilterCriteria:
    """The pre-filter reads the user's criteria; jobs never imports platform."""
    return PrefilterCriteria.from_settings(settings_service.read()["criteria"])


def build_container(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    secret_store: SecretStore | None = None,
    clock: Clock | None = None,
    llm_probe: LLMProbe | None = None,
    document_parser: DocumentParser | None = None,
    llm_client: LLMClient | None = None,
) -> Container:
    infra = _infra(settings, engine, secret_store, clock)
    llm = llm_client or OpenAiLLMClient(infra.settings_service.runtime)
    probe = llm_probe or ProviderProbe(
        client=llm,
        runtime=infra.settings_service.runtime,
        blocked_hosts=infra.settings.blocked_fetch_hosts,
    )
    cvs = CvService(
        session_factory=infra.session_factory,
        settings=infra.settings,
        clock=infra.clock,
        parser=document_parser
        or SubprocessParser(timeout_seconds=infra.settings.parser_timeout_seconds),
    )
    jobs = JobService(
        session_factory=infra.session_factory,
        clock=infra.clock,
        alert_source=_alert_source(infra.settings),
        criteria=lambda: _criteria(infra.settings_service),
    )
    steps = _steps(infra, llm)
    analysis = _analysis(infra, cvs=cvs, jobs=jobs, steps=steps)
    return _container(
        infra,
        cvs=cvs,
        jobs=jobs,
        llm=llm,
        steps=steps,
        analysis=analysis,
        tasks=_tasks(infra, analysis),
        llm_probe=probe,
    )


def _infra(
    settings: Settings | None,
    engine: Engine | None,
    secret_store: SecretStore | None,
    clock: Clock | None,
) -> _Infra:
    """The pieces every module shares. Built first, injected everywhere."""
    resolved = settings or Settings()
    resolved.ensure_dirs()
    engine = engine or create_db_engine(resolved.database_url)
    session_factory = create_session_factory(engine)
    store = secret_store or KeyringSecretStore()
    return _Infra(
        settings=resolved,
        engine=engine,
        session_factory=session_factory,
        clock=clock or SystemClock(),
        secret_store=store,
        settings_service=SettingsService(
            session_factory=session_factory,
            secret_store=store,
            defaults=resolved,
        ),
    )


def _steps(infra: _Infra, llm: LLMClient) -> Steps:
    return build_steps(
        infra.settings,
        session_factory=infra.session_factory,
        clock=infra.clock,
        llm=llm,
    )


def _analysis(
    infra: _Infra, *, cvs: CvService, jobs: JobService, steps: _Steps
) -> AnalysisService:
    structurer, matcher, suggester, cover_writer = steps
    return AnalysisService(
        pipeline=Pipeline(
            session_factory=infra.session_factory,
            cvs=cvs,
            jobs=jobs,
            structurer=structurer,
            matcher=matcher,
            suggester=suggester,
            cover_writer=cover_writer,
            prompts_dir=infra.settings.prompts_dir,
            model=infra.settings.llm_model,
            clock=infra.clock,
            constraints=lambda: _constraints(infra.settings_service),
        )
    )


def _tasks(infra: _Infra, analysis: AnalysisService) -> TaskService:
    return TaskService(
        session_factory=infra.session_factory,
        clock=infra.clock,
        # 0 means "no cap"; the user sets the real number in settings (FR-24).
        budget_monthly=lambda: int(
            infra.settings_service.read()["budget"]["monthly_tokens"] or 0
        ),
        probe=analysis.probe,
    )


def _platform(
    infra: _Infra, llm_probe: LLMProbe | None
) -> tuple[SafeFetcher, HealthService, DataControlsService]:
    return (
        SafeFetcher(blocked_hosts=infra.settings.blocked_fetch_hosts),
        HealthService(
            session_factory=infra.session_factory,
            secret_store=infra.secret_store,
            clock=infra.clock,
            llm_probe=llm_probe,
        ),
        DataControlsService(
            session_factory=infra.session_factory,
            engine=infra.engine,
            settings=infra.settings,
            clock=infra.clock,
        ),
    )


def _worker(
    infra: _Infra, *, analysis: AnalysisService, tasks: TaskService
) -> Worker:
    return Worker(
        analysis=analysis,
        tasks=tasks,
        poll_seconds=infra.settings.worker_poll_seconds,
        stale_seconds=infra.settings.task_stale_seconds,
    )


def _container(
    infra: _Infra,
    *,
    cvs: CvService,
    jobs: JobService,
    llm: LLMClient,
    steps: _Steps,
    analysis: AnalysisService,
    tasks: TaskService,
    llm_probe: LLMProbe | None,
) -> Container:
    structurer, matcher, suggester, cover_writer = steps
    http, health, data_controls = _platform(infra, llm_probe)
    return Container(
        settings=infra.settings,
        engine=infra.engine,
        session_factory=infra.session_factory,
        clock=infra.clock,
        secret_store=infra.secret_store,
        http=http,
        health=health,
        settings_service=infra.settings_service,
        data_controls=data_controls,
        cvs=cvs,
        jobs=jobs,
        llm=llm,
        jd_structurer=structurer,
        matcher=matcher,
        suggester=suggester,
        cover_writer=cover_writer,
        analysis=analysis,
        tasks=tasks,
        worker=_worker(infra, analysis=analysis, tasks=tasks),
    )
