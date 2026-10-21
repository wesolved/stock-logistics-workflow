# Copyright 2020 Camptocamp (https://www.camptocamp.com)
# Copyright 2020-2021 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _align_reference_carrier(self):
        """Keep the carrier of the references and of the other open transfers
        of those references aligned with the carrier of the transfers"""
        for picking in self:
            carrier = picking.carrier_id
            references = picking.move_ids.reference_ids
            if not references:
                continue
            references.carrier_id = carrier
            domain = [
                ("move_ids.reference_ids", "in", references.ids),
                ("state", "not in", ("done", "cancel")),
                ("carrier_id", "!=", carrier.id),
                ("carrier_id", "!=", False),
            ]
            need_align_pickings = self.search(domain).with_context(
                skip_align_reference_carrier=True
            )
            if need_align_pickings:
                need_align_pickings.carrier_id = carrier

    def write(self, values):
        if "carrier_id" not in values or self.env.context.get(
            "skip_align_reference_carrier"
        ):
            # We only track when carrier changes. Avoid useless computation when
            # carrier_id isn't in values
            return super().write(values)
        carrier_mapping = {record.id: record.carrier_id for record in self}
        res = super().write(values)
        # Align references on pickings where carrier was updated
        updated_pickings = self.filtered(
            lambda p: p.carrier_id != carrier_mapping.get(p.id)
        )
        if updated_pickings:
            updated_pickings._align_reference_carrier()
        return res
