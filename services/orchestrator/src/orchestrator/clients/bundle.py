from dataclasses import dataclass

import grpc
import httpx

from orchestrator.clients.competitor_analyst import CompetitorAnalystClient
from orchestrator.clients.http import AnalystClient, WriterClient
from orchestrator.clients.market_analyst import MarketAnalystClient
from orchestrator.clients.protocols import (
    AnalystClientProtocol,
    CompetitorAnalystClientProtocol,
    MarketAnalystClientProtocol,
    WriterClientProtocol,
)
from orchestrator.config import OrchestratorSettings


@dataclass(slots=True)
class OrchestratorClients:
    market_analyst: MarketAnalystClientProtocol
    competitor_analyst: CompetitorAnalystClientProtocol
    analyst: AnalystClientProtocol
    writer: WriterClientProtocol
    _http_client: httpx.AsyncClient | None = None
    _grpc_channel: grpc.aio.Channel | None = None

    @classmethod
    def create(cls, settings: OrchestratorSettings) -> "OrchestratorClients":
        http_client = httpx.AsyncClient(timeout=None)
        grpc_channel = (
            grpc.aio.secure_channel(
                settings.competitor_analyst_address, grpc.ssl_channel_credentials()
            )
            if settings.competitor_analyst_use_tls
            else grpc.aio.insecure_channel(settings.competitor_analyst_address)
        )
        return cls(
            market_analyst=MarketAnalystClient(settings.market_analyst_url),
            competitor_analyst=CompetitorAnalystClient(grpc_channel),
            analyst=AnalystClient(http_client, settings.analyst_url),
            writer=WriterClient(http_client, settings.writer_url),
            _http_client=http_client,
            _grpc_channel=grpc_channel,
        )

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
        if self._grpc_channel is not None:
            await self._grpc_channel.close()
