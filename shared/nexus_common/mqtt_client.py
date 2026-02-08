"""MQTT pub/sub support for NEXUS-A2A multi-transport (surveillance demo).

Requires: pip install aiomqtt (optional dependency).
Falls back gracefully if Mosquitto is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger("nexus.mqtt")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


async def mqtt_publish(
    topic: str,
    payload: Dict[str, Any],
    broker: str = MQTT_BROKER,
    port: int = MQTT_PORT,
    retain: bool = True,
) -> bool:
    """Publish a JSON payload to an MQTT topic. Returns True on success."""
    try:
        import aiomqtt  # noqa: F811

        async with aiomqtt.Client(broker, port=port) as client:
            await client.publish(topic, json.dumps(payload), retain=retain)
        logger.info("MQTT publish OK: %s", topic)
        return True
    except Exception as exc:
        logger.warning("MQTT publish failed (%s): %s", topic, exc)
        return False


async def mqtt_subscribe(
    topics: list[str],
    on_message: Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]],
    broker: str = MQTT_BROKER,
    port: int = MQTT_PORT,
    timeout: Optional[float] = None,
) -> None:
    """Subscribe to MQTT topics and invoke callback for each message."""
    try:
        import aiomqtt  # noqa: F811

        async with aiomqtt.Client(broker, port=port) as client:
            for t in topics:
                await client.subscribe(t)
            logger.info("MQTT subscribed: %s", topics)
            async for message in client.messages:
                topic_str = str(message.topic)
                data = json.loads(message.payload.decode("utf-8"))  # type: ignore[union-attr]
                await on_message(topic_str, data)
    except Exception as exc:
        logger.warning("MQTT subscribe failed: %s — falling back to HTTP", exc)
        raise


def mqtt_available() -> bool:
    """Check if MQTT broker env is configured."""
    return bool(os.getenv("MQTT_BROKER"))
