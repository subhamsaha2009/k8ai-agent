"""
Centralized logging configuration for k8ai.
All modules should import logger from here instead of using print().
"""

import logging
import sys

# Create module logger
logger = logging.getLogger("k8ai")

# Set default level (can be overridden by environment or config)
logger.setLevel(logging.INFO)

# Prevent adding multiple handlers
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        fmt='[%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

__all__ = ["logger"]
