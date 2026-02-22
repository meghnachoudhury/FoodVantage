import math

CONFIDENCE_NEUTRAL_VMS = 5.0
CONFIDENCE_TEMPERATURE = 1.6


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def row_confidence(row) -> float:
    """Estimate data confidence from nutrition completeness (0..1)."""
    cal = safe_float(row[2]) if len(row) > 2 else None
    sug = safe_float(row[3]) if len(row) > 3 else None
    fib = safe_float(row[4]) if len(row) > 4 else None
    prot = safe_float(row[5]) if len(row) > 5 else None
    fat = safe_float(row[6]) if len(row) > 6 else None
    sod = safe_float(row[7]) if len(row) > 7 else None

    risk_present = sum(v is not None and v > 0 for v in [cal, sug, fat, sod]) / 4.0
    all_present = sum(v is not None for v in [cal, sug, fib, prot, fat, sod]) / 6.0
    return max(0.0, min(1.0, 0.7 * risk_present + 0.3 * all_present))


def temperature_scale_confidence(confidence: float, temperature: float = CONFIDENCE_TEMPERATURE) -> float:
    """Calibrate confidence with temperature scaling on log-odds."""
    c = max(1e-4, min(1 - 1e-4, float(confidence)))
    t = max(1e-6, float(temperature))
    logit = math.log(c / (1 - c))
    scaled = 1 / (1 + math.exp(-(logit / t)))
    return max(0.0, min(1.0, scaled))


def confidence_weighted_score(raw_vms: float, confidence: float, neutral_vms: float = CONFIDENCE_NEUTRAL_VMS) -> float:
    """Pull low-confidence scores toward neutral using calibrated confidence."""
    conf_cal = temperature_scale_confidence(confidence)
    weighted = neutral_vms + ((raw_vms - neutral_vms) * conf_cal)
    return round(max(-2.0, min(10.0, weighted)), 1)
