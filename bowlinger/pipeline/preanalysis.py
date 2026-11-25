"""Summarise stumps, ball colour, the striker, and audio before delivery logic."""

from __future__ import annotations


def wicket_uprights(stumps: list[dict], frame_count: int) -> list[dict]:
    """Keep uprights that are seen repeatedly and stand in a set of two or three.

    A single pale speck, or a lone net pole, is not a wicket.
    """
    sampled = max(1, frame_count // 2)
    minimum_seen = max(3, int(0.12 * sampled))
    strong = [item for item in stumps if item["n"] >= minimum_seen and item["h"] >= 18]
    groups: list[dict] = []
    for stump in strong:
        for group in groups:
            if abs(stump["x"] - group["x"]) <= 70 and abs(stump["y"] - group["y"]) <= 90:
                count = group["n"] + 1
                group["x"] = (group["x"] * group["n"] + stump["x"]) / count
                group["y"] = (group["y"] * group["n"] + stump["y"]) / count
                group["n"] = count
                group["members"].append(stump)
                break
        else:
            groups.append({"x": stump["x"], "y": stump["y"], "n": 1, "members": [stump]})
    kept: list[dict] = []
    for group in groups:
        if 2 <= len(group["members"]) <= 4:
            kept.extend(group["members"])
    return kept


def summarise(scan: dict, audio: dict) -> dict:
    stumps = wicket_uprights(scan["stumps"], scan["frame_count"])
    stump_count = len(stumps)
    colors = [ball["color"] for ball in scan["balls"]]
    if not colors:
        ball_type = "unknown"
    else:
        red = colors.count("red")
        white = colors.count("white")
        ball_type = "red" if red >= white else "white"
    batsman_on_crease = False
    if stumps and scan["batsmen"]:
        stump_x = sum(item["x"] for item in stumps) / len(stumps)
        stump_y = sum(item["y"] for item in stumps) / len(stumps)
        stump_h = sum(item["h"] for item in stumps) / len(stumps)
        limit = max(80.0, stump_h * 2.5)
        for person in scan["batsmen"]:
            distance = ((person["x"] - stump_x) ** 2 + (person["y"] - stump_y) ** 2) ** 0.5
            if distance <= limit:
                batsman_on_crease = True
                break
    return {
        "stumps_detected": stump_count > 0,
        "stump_count": stump_count,
        "ball_type": ball_type,
        "batsman_on_crease": batsman_on_crease,
        "audio_present": bool(audio["present"]),
    }
