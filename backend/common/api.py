from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """DRF errors as {"detail": "...", "errors": {...}} so the frontend reads one shape."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict) and "detail" in data:
        response.data = {"detail": str(data["detail"]), "errors": {}}
    elif isinstance(data, dict):
        first = next(iter(data.values()), None)
        message = first[0] if isinstance(first, list) and first else "Check the highlighted fields."
        response.data = {"detail": str(message), "errors": data}
    else:
        response.data = {"detail": str(data[0]) if data else "Something went wrong.", "errors": {}}
    return response
