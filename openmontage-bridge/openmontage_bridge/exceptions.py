"""Custom exceptions for OpenMontage Bridge."""


class BridgeError(Exception):
    """Base error for all bridge-level failures."""


class OpenMontageNotFound(BridgeError):
    """OpenMontage project directory not found."""


class OpenMontageNotSetup(BridgeError):
    """OpenMontage .venv missing — run make setup first."""


class ToolCallError(BridgeError):
    """Error during tool execution."""


class PipelineError(BridgeError):
    """Error during pipeline execution."""


class DiscoveryError(BridgeError):
    """Error during capability discovery."""
