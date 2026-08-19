from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_status = fields.Selection([
        ('lead', 'Lead'),
        ('prospect', 'Prospect'),
        ('client', 'Client'),
        ('ancien_client', 'Ancien client'),
    ], string='Statut', default='lead', tracking=True, index=True)
