import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from template_router import template_router  # noqa: E402


def test_named_template_fill_post_routes_precede_template_id_route():
    """FastAPI matches routes in registration order.

    The generic ``/template/{tid}`` assignment route must stay after named
    Template Fill POST endpoints; otherwise ``llm-suggest`` and
    ``extract-from-document`` are parsed as template ids.
    """
    post_paths = [
        route.path
        for route in template_router.routes
        if "POST" in getattr(route, "methods", set())
        and route.path.startswith("/api/{dataset_id}/template/")
    ]

    generic_index = post_paths.index("/api/{dataset_id}/template/{tid}")
    assert post_paths.index("/api/{dataset_id}/template/llm-suggest") < generic_index
    assert post_paths.index("/api/{dataset_id}/template/extract-from-document") < generic_index
