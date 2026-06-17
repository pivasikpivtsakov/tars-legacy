import uvicorn

from api.app import app
from common.environment import API_HOST, API_PORT
from common.logging_config import setup_logging

setup_logging()

uvicorn.run(app, host=API_HOST, port=API_PORT, log_config=None)
