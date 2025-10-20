import asyncio
import math
from typing import Optional, Any
from aws_bedrock_token_generator import provide_token
from core.logging_config import get_logger
from core.config import harvester_settings
logger = get_logger(__name__)

token_expiry = harvester_settings.bedrock_token_expiry_seconds # obtain expiry time from settings
REFRESH_SECONDS = math.floor(token_expiry - ( token_expiry / 6 )) # give headroom so always before expiry
BEDROCK_TOKEN = None
_app: Optional[Any] = None

def set_app(app: Any) -> None:
    global _app
    _app = app

def get_app() -> Any:
    if _app is None:
        raise RuntimeError("App not set yet. Did lifespan run and call set_app(app)?")
    return _app

class BedrockToken:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = asyncio.Event()

    async def get_token(self):
        app = get_app()
        # Check if the token exists, if not, generate it
        if not hasattr(app.state, 'bedrock_api_token') or app.state.bedrock_api_token is None:
            logger.debug("BEDROCK:BedrockToken:get_token: Token not found, generating new token.")
            token = provide_token()
            app.state.bedrock_api_token = token
        return app.state.bedrock_api_token

    async def _run(self) -> None:
        global BEDROCK_TOKEN
        while True:
            try:
                logger.debug("BEDROCK:BedrockToken:_run: Refreshing Bedrock token.")
                app = get_app()
                BEDROCK_TOKEN = provide_token()
                app.state.bedrock_api_token = BEDROCK_TOKEN
                logger.info("BEDROCK:BedrockToken:_run: Token refreshed successfully.")
                await asyncio.sleep(REFRESH_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"BEDROCK:BedrockToken:_run: Failed to refresh Bedrock token: {e}")
                # Optional: backoff on error, keep last good token
                await asyncio.sleep(300)

    async def start(self):
        logger.debug("BEDROCK:BedrockToken:start: Starting AWS Bedrock Token task.")
        self._running.set()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running.clear()
        if self._task:
            self._task.cancel()
            try:
                logger.debug("BEDROCK:BedrockToken:stop: Stopping AWS Bedrock Token task.")
                await self._task
            except asyncio.CancelledError:
                pass
