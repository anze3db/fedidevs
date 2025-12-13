from django.core.exceptions import BadRequest


def get_validated_page_number(request):
    page_number = request.GET.get("page")
    if page_number is None or page_number == "":
        return None
    if not isinstance(page_number, str):
        raise BadRequest("Invalid page number.")
    # Disallow NUL bytes and non-digit input
    if "\x00" in page_number or not page_number.isdigit():
        raise BadRequest("Invalid page number.")
    return int(page_number)
