# server package
# server.py(FastAPI app)가 server/ 패키지로 가려진 문제를 해소한다.
import importlib.util as _ilu
import pathlib as _pl

_server_py = _pl.Path(__file__).parent.parent / "server.py"
_spec = _ilu.spec_from_file_location("ai_orchestrator._server_module", _server_py)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
app = _mod.app
