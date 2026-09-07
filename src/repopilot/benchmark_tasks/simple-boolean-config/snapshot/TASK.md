Parse booleans in src/config.py: strip and casefold strings; true/1/yes/on map to True, false/0/no/off map to False; anything else raises ValueError.
