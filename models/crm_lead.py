from odoo import models, fields, api

STATUS_RANK = {'lead': 0, 'prospect': 1, 'client': 2, 'ancien_client': 3}


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    partner_status = fields.Selection(
        related='partner_id.partner_status',
        store=True,
        readonly=False,
        string='Statut contact',
    )

    def _target_status(self):
        self.ensure_one()
        if self.stage_id and self.stage_id.is_won:
            return 'client'
        if self.type == 'opportunity':
            return 'prospect'
        return 'lead'

    def _upgrade_partner_status(self):
        self.ensure_one()
        if not self.partner_id:
            return
        target = self._target_status()
        current = self.partner_id.partner_status or 'lead'
        if STATUS_RANK.get(target, -1) > STATUS_RANK.get(current, -1):
            self.partner_id.partner_status = target

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        for lead in leads:
            lead._upgrade_partner_status()
        return leads

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals or 'type' in vals:
            for lead in self:
                lead._upgrade_partner_status()
        return res

    def action_recompute_partner_status(self):
        for lead in self:
            lead._upgrade_partner_status()
