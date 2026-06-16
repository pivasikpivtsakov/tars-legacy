import uvicorn  # noqa: E402

from api.app import app  # noqa: E402
from common.environment import API_HOST, API_PORT  # noqa: E402
from common.logging_config import setup_logging  # noqa: E402

setup_logging()

uvicorn.run(app, host=API_HOST, port=API_PORT, log_config=None)
