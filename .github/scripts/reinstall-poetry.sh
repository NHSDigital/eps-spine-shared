#!/bin/bash

poetry_tool_version=$(grep poetry .tool-versions)
poetry_version=${poetry_tool_version//"poetry "}
asdf uninstall poetry "$poetry_version"
asdf install poetry
