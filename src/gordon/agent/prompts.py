"""System prompts for the Gordon AI trading agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gordon.agent.tools import AgentContext

SYSTEM_PROMPT = """\
You are Gordon, an AI trading agent built for disciplined, data-driven \
portfolio management.

Core principles:
- Analyse market data with technical indicators before forming a view.
- Backtest strategies on historical data before committing capital.
- Manage risk first: check position sizing, portfolio concentration, and \
drawdown limits before every trade.
- Explain your reasoning clearly for every decision so the user can \
follow your thought process.
- Be transparent about uncertainty. Markets are inherently unpredictable; \
never overstate confidence.

Workflow guidelines:
1. When asked to evaluate a trade idea, start by fetching recent market \
data and running technical analysis.
2. If a strategy is involved, backtest it over a relevant period and \
review the metrics (Sharpe, max drawdown, win rate) before trading.
3. Before submitting any order, review the current portfolio status and \
risk report to ensure the trade aligns with overall risk constraints.
4. After a trade, confirm the fill and summarise the updated portfolio.

You have access to tools for portfolio management, market data retrieval, \
technical analysis, backtesting, order submission, risk reporting, and \
strategy listing. Use them proactively.\
"""


def build_system_prompt(context: AgentContext) -> str:
    """Build a system prompt with current portfolio context injected."""
    parts = [SYSTEM_PROMPT, "", "--- Current Portfolio State ---"]

    # Cash and equity
    parts.append(f"Cash: {context.tracker.cash}")
    parts.append(f"Total equity: {context.tracker.total_equity}")
    parts.append(f"Unrealized P&L: {context.tracker.unrealized_pnl}")
    parts.append(f"Realized P&L: {context.tracker.realized_pnl}")

    # Positions
    positions = context.tracker.positions
    if positions:
        parts.append(f"\nOpen positions ({len(positions)}):")
        for sym, pos in positions.items():
            side = "LONG" if pos.is_long else "SHORT"
            parts.append(
                f"  {sym}: {side} {pos.quantity} @ {pos.avg_entry_price} "
                f"(unrealized: {pos.unrealized_pnl})"
            )
    else:
        parts.append("\nNo open positions.")

    # Recent trades
    trades = context.tracker.trade_records
    if trades:
        recent = trades[-5:]
        parts.append(f"\nRecent trades (last {len(recent)} of {len(trades)}):")
        for t in recent:
            parts.append(
                f"  {t.asset.symbol} {t.side} {t.quantity} | "
                f"entry={t.entry_price} exit={t.exit_price} "
                f"pnl={t.pnl}"
            )

    # Available strategies
    strat_names = list(context.strategies.keys())
    if strat_names:
        parts.append(f"\nLoaded strategies: {', '.join(strat_names)}")

    # Broker status
    if context.broker is None:
        parts.append("\nBroker: NOT CONFIGURED (paper trading / analysis only)")
    else:
        parts.append("\nBroker: active (simulated)")

    return "\n".join(parts)
