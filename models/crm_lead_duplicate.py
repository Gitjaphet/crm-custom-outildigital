from odoo import fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    partner_duplicate_status = fields.Selection(
        related='partner_id.duplicate_status',
        store=True,
        string='Doublon contact',
    )