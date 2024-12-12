"""Web scraper tool."""

import json
import logging

import trafilatura
from homeassistant.core import HomeAssistant

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

    @llm_tool(hass)
    def web_scrape(url: str):
        """Get latest content of a web page."""
        downloaded = trafilatura.fetch_url(url=url)

        parsed = trafilatura.extract(
            downloaded,
            url=url,
            output_format="json",
            include_links=True,
            deduplicate=True,
            favor_precision=False,
            favor_recall=True,
            with_metadata=True,
        )

        result = json.loads(parsed)

        return {k: v for k, v in result.items() if v and k not in REMOVE_KEYS}
