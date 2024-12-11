"""Web scraper tool."""

import json
import logging

import trafilatura
from homeassistant.core import HomeAssistant

from ..llm_tools import llm_tool

_LOGGER = logging.getLogger(__name__)


def setup(hass: HomeAssistant):
    """Register the tool on integration startup."""

    @llm_tool(hass)
    def web_scrape(url: str):
        """Get latest content of a web page."""
        downloaded = trafilatura.fetch_url("linux.org.ru")

        parsed = trafilatura.extract(
            downloaded,
            output_format="json",
            include_links=True,
            deduplicate=True,
            favor_precision=True,
        )

        result = json.loads(parsed)

        if "comments" in result and not result["comments"]:
            del result["comments"]

        return result
