def materialize(events):
    return {e["key"]: e.get("value") for e in events}
