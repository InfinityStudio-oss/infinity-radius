"""Top-level Selcom integration facade — composes the Collection
(customer -> platform payments) and Disbursement (platform -> tenant
payouts) sub-clients behind one object, so callers construct a single
`SelcomClient(config)` rather than importing each sub-service directly.

See collection.py and disbursement.py for what each API actually does
(and does not yet) support, and authentication.py/signatures.py for what
remains a documented TODO pending Selcom's official API documentation.
"""

from app.integrations.selcom.collection import CollectionService
from app.integrations.selcom.config import SelcomConfig
from app.integrations.selcom.disbursement import SelcomDisbursementService


class SelcomClient:
    def __init__(self, config: SelcomConfig) -> None:
        self.collection = CollectionService(config)
        self.disbursement = SelcomDisbursementService(config)
