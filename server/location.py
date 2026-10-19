"""Works out where an alert came from."""
import config


def resolve(msg, reference, now):
    """Returns a dict with latitude, longitude, accuracy, floor and source.

    GPS wins if the message has it. Otherwise the floor comes from comparing the
    Fob's pressure with the latest Reference reading. Otherwise there is no location."""
    if msg.get("lat") is not None and msg.get("lon") is not None:
        return {
            "latitude": msg["lat"] / 1_000_000,
            "longitude": msg["lon"] / 1_000_000,
            "accuracy": msg.get("acc"),
            "floor": None,
            "source": "gps",
        }

    pressure = msg.get("p")
    if pressure is not None and reference is not None:
        if now - reference["timestamp"] <= config.REF_MAX_AGE_S:
            # Higher floors have lower pressure, so reference minus Fob is positive upstairs.
            floors_up = round((reference["pressure"] - pressure) / config.PA_PER_FLOOR)
            floor = max(1, min(config.MAX_FLOOR, 1 + floors_up))
            return {"latitude": None, "longitude": None, "accuracy": None,
                    "floor": floor, "source": "floor"}

    return {"latitude": None, "longitude": None, "accuracy": None,
            "floor": None, "source": "none"}
