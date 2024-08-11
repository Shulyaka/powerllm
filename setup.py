"""Setup module for powerllm."""

import pathlib

from setuptools import find_packages, setup

VERSION = "0.0.1"


def long_description():
    """Read README.md file."""
    f = (pathlib.Path(__file__).parent / "README.md").open()
    res = f.read()
    f.close()
    return res  # noqa: R504


setup(
    name="powerllm",
    version=VERSION,
    description="Home Assistant custom component " "to empower LLM integrations",
    long_description=long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/Shulyaka/powerllm",
    author="Denis Shulyaka",
    author_email="ds_github@shulyaka.org.ru",
    license="GNU General Public License v3.0",
    keywords="homeassistant home-assistant llm generative ai chatgpt chat gpt gemini",
    packages=find_packages(exclude=["tests"]),
    python_requires=">=3.12",
    tests_require=["pytest"],
)
