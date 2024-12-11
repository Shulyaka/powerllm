"""Test web scrape tool."""

from unittest.mock import patch


def test_test(hass):
    """Workaround for https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/discussions/160."""


async def test_web_scrape_tool(async_call_tool) -> None:
    """Test web scrape tool."""

    helloworld = """<!DOCTYPE html>
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

    with patch("trafilatura.fetch_url", return_value=helloworld):
        response = await async_call_tool("web_scrape", url="example.com")

    assert response == {"text": "This is a simple HTML page with a greeting message."}
