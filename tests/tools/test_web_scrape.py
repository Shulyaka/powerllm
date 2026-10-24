"""Test web scrape tool."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError


async def test_web_scrape_tool(async_call_tool) -> None:
    """Test web scrape tool."""

    helloworld = MagicMock()
    helloworld.status = 200
    helloworld.url = "example.com"
    helloworld.data = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hello World</title>
</head>
<body>
    <h1>Hello, World!</h1>
    <p>This is a simple HTML page with a greeting message.</p>
</body>
</html>
"""

    with patch("trafilatura.fetch_response", return_value=helloworld) as mock_fetch:
        response = await async_call_tool("web_scrape", url="example.com")

    mock_fetch.assert_called_once_with(url="example.com")
    assert response == {
        "title": "Hello, World!",
        "text": "Hello, World!\nThis is a simple HTML page with a greeting message.",
    }


@pytest.mark.parametrize("downloaded", [None, MagicMock(data=b"")])
async def test_web_scrape_download_error(async_call_tool, downloaded) -> None:
    """Report missing downloads without dereferencing a missing response."""
    with patch("trafilatura.fetch_response", return_value=downloaded), patch(
        "trafilatura.extract"
    ) as extract:
        with pytest.raises(HomeAssistantError, match="No data downloaded"):
            await async_call_tool("web_scrape", url="https://example.com")

    extract.assert_not_called()


async def test_web_scrape_parse_error(async_call_tool) -> None:
    """Report failed text extraction through HA's exception handling."""
    downloaded = MagicMock(data=b"unparsable response")
    with patch("trafilatura.fetch_response", return_value=downloaded), patch(
        "trafilatura.extract", return_value=None
    ):
        with pytest.raises(HomeAssistantError, match="No data parsed"):
            await async_call_tool("web_scrape", url="https://example.com")
