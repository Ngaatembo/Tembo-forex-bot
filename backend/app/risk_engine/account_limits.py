"""
Account-level risk limit checks. Each function is independent and
fails closed — a missing/invalid input never passes silently.
"""

from app.risk_engine.risk_models import AccountState, RiskLimitsConfig


def account_data_valid(account: AccountState) -> tuple[bool, str]:
    if account.equity is None or account.equity <= 0:
        return False, "Account equity is missing or non-positive."
    if account.peak_equity is None or account.peak_equity <= 0:
        return False, "Peak equity (required for drawdown calculation) is missing or non-positive."
    if account.daily_start_equity is None or account.daily_start_equity <= 0:
        return False, "Daily start equity (required for daily-loss calculation) is missing or non-positive."
    return True, "Account data valid."


def check_per_trade_risk(risk_pct: float, limits: RiskLimitsConfig) -> tuple[bool, str]:
    if risk_pct > limits.max_risk_per_trade_pct:
        return False, f"Proposed position risks {risk_pct:.2%} of equity, exceeding configured {limits.max_risk_per_trade_pct:.2%} maximum."
    return True, f"Per-trade risk {risk_pct:.2%} within {limits.max_risk_per_trade_pct:.2%} maximum."


def check_total_open_risk(account: AccountState, new_trade_risk_pct: float, limits: RiskLimitsConfig) -> tuple[bool, str]:
    combined = account.total_open_risk_pct + new_trade_risk_pct
    if combined > limits.max_total_open_risk_pct:
        return False, f"Combined open risk would reach {combined:.2%}, exceeding configured {limits.max_total_open_risk_pct:.2%} maximum."
    return True, f"Combined open risk {combined:.2%} within {limits.max_total_open_risk_pct:.2%} maximum."


def check_daily_loss(account: AccountState, limits: RiskLimitsConfig) -> tuple[bool, str]:
    daily_pnl = account.daily_realized_pnl + account.daily_unrealized_pnl
    if daily_pnl >= 0:
        return True, "No daily loss."
    loss_pct = abs(daily_pnl) / account.daily_start_equity
    if loss_pct >= limits.max_daily_loss_pct:
        return False, f"Daily loss {loss_pct:.2%} has reached the configured {limits.max_daily_loss_pct:.2%} maximum — DO_NOT_TRADE."
    return True, f"Daily loss {loss_pct:.2%} within {limits.max_daily_loss_pct:.2%} maximum."


def check_drawdown(account: AccountState, limits: RiskLimitsConfig) -> tuple[bool, str]:
    drawdown_pct = (account.peak_equity - account.equity) / account.peak_equity
    if drawdown_pct >= limits.max_drawdown_pct:
        return False, f"Account drawdown {drawdown_pct:.2%} has reached the configured {limits.max_drawdown_pct:.2%} maximum — DO_NOT_TRADE."
    return True, f"Drawdown {drawdown_pct:.2%} within {limits.max_drawdown_pct:.2%} maximum."


def check_position_limit(account: AccountState, limits: RiskLimitsConfig) -> tuple[bool, str]:
    if account.open_positions_count >= limits.max_simultaneous_positions:
        return False, f"{account.open_positions_count} positions already open, at the configured maximum of {limits.max_simultaneous_positions}."
    return True, f"{account.open_positions_count}/{limits.max_simultaneous_positions} positions open."


def check_exposure(position_size: float, entry_price: float, account: AccountState, limits: RiskLimitsConfig) -> tuple[bool, str]:
    notional = position_size * entry_price
    exposure_pct = notional / account.equity
    if exposure_pct > limits.max_exposure_pct:
        return False, f"Proposed notional exposure {exposure_pct:.2%} of equity exceeds configured {limits.max_exposure_pct:.2%} maximum."
    return True, f"Exposure {exposure_pct:.2%} within {limits.max_exposure_pct:.2%} maximum."
