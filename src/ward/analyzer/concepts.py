from enum import Enum


class Concept(Enum):
    IMPORT = "import"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    LOOP = "loop"
    ASYNC_CALL = "async_call"
    EXCEPTION_HANDLER = "exception_handler"
    FUNCTION_CALL = "function_call"
    VARIABLE_ASSIGNMENT = "variable_assignment"
    AWAIT = "await"
    QUERY_CALL = "query_call"
    IO_CALL = "io_call"
    EXCEPTION_TYPE = "exception_type"
    WITH_STATEMENT = "with_statement"
