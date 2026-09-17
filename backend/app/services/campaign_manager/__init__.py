"""CampaignManager package — thin facade over focused campaign services.

Modules:
  - facade:         CampaignManager core (lifecycle, properties, persistence)
  - facades:        anchor/context passthrough mixin
  - recap_advancer: recap + turn/session/arc advancement mixin
  - metrics:        token budget, per-turn metrics mixin
"""

from app.services.campaign_manager.facade import CampaignManager

__all__ = ["CampaignManager"]
