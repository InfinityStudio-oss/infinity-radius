"""Top-level legacy Selcom integration facade.

Only the Disbursement (platform -> tenant payouts) sub-client remains
here, and it is still a documented TODO pending Selcom's official API
documentation — see disbursement.py and authentication.py/signatures.py.

Collection (customer -> platform payments) is NOT here: it is fully
implemented against Selcom Mobile Checkout in
app/integrations/selcom_collection/, orchestrated by
app/services/selcom_payment_provider.py. The never-implementable
Collection stub that used to live alongside this facade was removed once
that integration was validated in production.
"""

from app.integrations.selcom.config import SelcomConfig
from app.integrations.selcom.disbursement import SelcomDisbursementService


class SelcomClient:
    def __init__(self, config: SelcomConfig) -> None:
        self.disbursement = SelcomDisbursementService(config)
