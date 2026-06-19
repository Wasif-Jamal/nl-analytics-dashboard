"""Tests for app.services.sql_service.QueryService.

Covers the ``database-access-boundary`` requirement: the service delegates
execution to the repository (the only DB pathway) and returns its QueryResult.
"""

from unittest.mock import MagicMock

import pandas as pd

from app.repositories.query_repository import QueryRepository
from app.schemas.sql_result import QueryResult
from app.services.sql_service import QueryService


def test_run_query_delegates_to_repository():
    """run_query forwards the SQL to the repository and returns its result."""
    expected = QueryResult(
        dataframe=pd.DataFrame({"n": [1]}), columns=["n"], row_count=1
    )
    repository = MagicMock(spec=QueryRepository)
    repository.execute_select.return_value = expected

    service = QueryService(repository=repository)
    result = service.run_query("SELECT COUNT(*) AS n FROM customers")

    repository.execute_select.assert_called_once_with(
        "SELECT COUNT(*) AS n FROM customers"
    )
    assert result is expected
