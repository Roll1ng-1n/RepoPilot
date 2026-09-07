def summarize(values):
    return {"count": len(values), "mean": sum(values) / len(values), "maximum": max(0, *values)}
