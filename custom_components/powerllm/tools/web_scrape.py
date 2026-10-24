"""Web scraper tool."""

import json
import logging

import trafilatura
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

from ..llm_tools import llm_tool

_LOGGER = logging.getLogger(__name__)


REMOVE_KEYS = {
    "hostname",
    "fingerprint",
    "id",
    "raw_text",
    "language",
    "image",
    "pagetype",
    "filedate",
    "source",
    "source-hostname",
    "tags",
}


def setup(hass: HomeAssistant):
    """Register the tool on integration startup."""

    @llm_tool(
        hass,
        title="Read a web page",
        annotations=llm.ToolAnnotations(
            read_only=True, destructive=False, idempotent=True, open_world=True
        ),
    )
    def web_scrape(url: str):
        """Get text from a web page.

        Use it to get up-to-date information from the internet.
        """
        downloaded = trafilatura.fetch_response(url=url)

        if downloaded and downloaded.data:
            parsed = trafilatura.extract(
                downloaded.data,
                url=downloaded.url,
                output_format="json",
                include_links=True,
                deduplicate=True,
                favor_precision=False,
                favor_recall=True,
                with_metadata=True,
            )
            if not parsed:
                raise HomeAssistantError("No data parsed.")
            result = json.loads(parsed)
        else:
            raise HomeAssistantError("No data downloaded.")

        result = {k: v for k, v in result.items() if v and k not in REMOVE_KEYS}

        if downloaded.url != url:
            result["url"] = downloaded.url

        if downloaded.status != 200:
            result["status"] = downloaded.status

        return result
