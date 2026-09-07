Fix the CSV export flow: schema.fields must be [name,note]; render(rows) must emit that header and correctly quote commas, quotes and embedded newlines using LF row endings, preserving Unicode.
