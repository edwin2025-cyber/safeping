# Floor survey results

Not run yet. There is no survey data.

`tests/survey_analyze.py` writes this file after the survey walk (see `docs/reference-survey-changes.md`, "Your plan", step 5). It replaces everything here with:

- heights by building and floor (mean, min, max, count), in meters above the Reference board
- the gap between neighboring floors in each building, and whether they can be told apart with margin
- WiFi: the access points seen on each floor, and how often the strongest one points to the right building
- every matched point, and the marks and points that did not match
