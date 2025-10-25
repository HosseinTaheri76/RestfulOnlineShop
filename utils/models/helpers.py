def get_prefetched(obj, attr_name, fallback_qs):
    """
    Return prefetched objects from `attr_name` if available,
    otherwise evaluate and return the given fallback queryset as a list.
    """
    items = getattr(obj, attr_name, None)
    if items is not None:
        return items
    return list(fallback_qs)
