def parse_rows(text):
    return dict(line.split("=") for line in text.splitlines())
