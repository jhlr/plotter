# One-word entry points. PORT is only needed to flash (macOS: /dev/cu.usbserial-*, Linux: /dev/ttyUSB0, Windows: COM3).
PORT ?=

.PHONY: setup check servotest servoloop flash sim firmware-build
setup:          ## install the Python side (and run the tests)
	cd server && uv sync --all-extras && uv run pytest -q
check:          ## types + tests, no hardware
	cd server && uv run mypy src && uv run pytest -q
servotest:      ## flash the standalone servo test, then open the monitor
	cd firmware && pio run -e servotest_uno -t upload $(if $(PORT),--upload-port $(PORT)) && pio device monitor -b 57600
servoloop:      ## flash the stand-alone motor test (servos sweep in a loop by themselves)
	cd firmware && pio run -e servoloop_uno -t upload $(if $(PORT),--upload-port $(PORT))
flash:          ## flash the real firmware (look for "verified" at the end)
	cd firmware && pio run -e uno -t upload $(if $(PORT),--upload-port $(PORT))
firmware-build: ## compile every firmware env, no board needed
	cd firmware && pio run
sim:            ## run the MCP server against the built-in simulator
	cd server && uv run penarm-mcp
