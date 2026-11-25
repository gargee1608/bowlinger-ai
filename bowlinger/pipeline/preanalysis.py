"""Summarise stumps, ball colour, the striker, and audio before delivery logic."""

from __future__ import annotations


def summarise(scan: dict, audio: dict) -> dict:
    stumps = [item for item in scan["stumps"] if item["n"] >= 2]
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
