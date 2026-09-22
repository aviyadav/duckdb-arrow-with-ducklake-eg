import os
import shutil
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from loguru import logger as log
from sqlmesh.core.context import Context

from shared.settings import LOCAL_DIR, env
from shared.storage import Storage, StoragePrefix

SQLMESH_PROJECT_DIR = str((Path(__file__).parents[1] / "transform").resolve())
DOCS_PORT = 8080


class SQLMeshHandler:
    """Runs the SQLMesh project in `transform/`, replacing the original dbt handler."""

    def __init__(self, debug: bool = False):
        self.debug = debug

        os.environ["LOCAL_DIR"] = LOCAL_DIR

        # Point RAW__* variables at the latest ingested datasets, so SQLMesh renders
        # the models against the most recent versions in object storage.
        s = Storage(prefix=StoragePrefix.INGEST)
        s.latest_to_env()

        self.mkdirs()

        self.context = Context(paths=SQLMESH_PROJECT_DIR)

    def mkdirs(self):
        engine_db_dir = os.path.dirname(os.path.join(LOCAL_DIR, env.str("ENGINE_DB")))
        os.makedirs(engine_db_dir, exist_ok=True)

    @staticmethod
    def _selection(models: Optional[tuple[str, ...]]) -> Optional[list[str]]:
        # dlctl accepts the same upstream/downstream selectors as SQLMesh, e.g. +model
        return list(models) if models else None

    def selected_models(
        self, selection: Optional[list[str]]
    ) -> Optional[list[str]]:
        """Resolve a selector, such as `+graphs.music_taste.*`, into model names.

        Audits are addressed by model name while plans accept selectors, and SQLMesh
        only expands selectors internally, so the same helper is reused here.
        """
        if not selection:
            return None

        return sorted(
            self.context._select_models_for_run(
                selection,
                no_auto_upstream=True,
                snapshots=self.context.snapshots.values(),
            )
        )

    def run(self, models: Optional[tuple[str, ...]] = None):
        log.info("Planning SQLMesh models: {}", self._selection(models) or "all")

        plan = self.context.plan(
            auto_apply=True,
            no_prompts=True,
            skip_tests=True,
            skip_linter=True,
            select_models=self._selection(models),
        )

        if plan is None:
            log.info("No changes to apply")
            return

        for new_snapshot in plan.new_snapshots:
            log.info("{}: added", new_snapshot.name)
        for modified_snapshot in plan.modified_snapshots:
            log.info("{}: modified", modified_snapshot.name)

        log.info("Applied changes to environment: {}", plan.environment.name)

    def test(self, models: Optional[tuple[str, ...]] = None):
        selection = self._selection(models)

        log.info("Running audits: {}", selection or "all")

        model_names = self.selected_models(selection)

        passed = self.context.audit(
            start=None,
            end=None,
            models=iter(model_names) if model_names else None,
        )

        if passed:
            log.info("All audits passed")
        else:
            log.warning("Some audits failed")

        return passed

    def docs_generate(self) -> str:
        docs_dir = Path(LOCAL_DIR) / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        output_path = docs_dir / "index.html"

        log.info("Generating model documentation (DAG) to {}", output_path)

        self.context.render_dag(str(output_path))

        return str(output_path)

    def docs_serve(self, port: int = DOCS_PORT):
        docs_dir = Path(LOCAL_DIR) / "docs"

        if not (docs_dir / "index.html").exists():
            self.docs_generate()

        log.info("Serving documentation at http://localhost:{}", port)
        log.info("Press Ctrl+C to stop")

        handler = partial(SimpleHTTPRequestHandler, directory=str(docs_dir))

        with ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                log.info("Documentation server stopped")

    def clean(self):
        log.info("Cleaning SQLMesh cache")

        shutil.rmtree(Path(SQLMESH_PROJECT_DIR) / ".cache", ignore_errors=True)
