"""Expected domain failures and transport-neutral exit semantics."""

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    REVIEW_REQUIRED = 2
    INPUT_ERROR = 3
    PROVIDER_ERROR = 4
    SCHEMA_ERROR = 5


class DDEError(Exception):
    exit_code = ExitCode.SCHEMA_ERROR


class InputError(DDEError):
    exit_code = ExitCode.INPUT_ERROR


class UnsupportedInputError(InputError):
    pass


class CorruptInputError(InputError):
    pass


class EncryptedPDFError(InputError):
    pass


class InputLimitError(InputError):
    pass


class ProviderError(DDEError):
    exit_code = ExitCode.PROVIDER_ERROR


class ProviderConfigurationError(ProviderError):
    pass


class ProviderRequestError(ProviderError):
    pass


class SchemaOutputError(DDEError):
    exit_code = ExitCode.SCHEMA_ERROR
