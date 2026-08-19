import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    duplicate_status = fields.Selection([
        ('none', 'Aucun'),
        ('name', 'Nom similaire'),
        ('phone', 'Telephone identique'),
        ('email', 'Email identique'),
    ], string='Doublon', default='none', index=True)

    @staticmethod
    def _normalize_text(s):
        if not s:
            return ''
        s = s.strip().lower()
        accents = {'à': 'a', 'â': 'a', 'ä': 'a', 'á': 'a', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
                   'î': 'i', 'ï': 'i', 'ô': 'o', 'ö': 'o', 'ù': 'u', 'û': 'u', 'ü': 'u', 'ç': 'c'}
        for k, v in accents.items():
            s = s.replace(k, v)
        return s

    @staticmethod
    def _normalize_name(name):
        s = ResPartner._normalize_text(name)
        for suffix in [' sarlu', ' sarl', ' sa ', ' eirl', ' ste ', ' societe',
                       ' entreprise', ' etablissement', ' ets ']:
            s = s.replace(suffix, ' ')
        for ch in ['.', ',', '-', "'", '"', '(', ')', '/', ':', ';']:
            s = s.replace(ch, ' ')
        return ' '.join(s.split())

    @staticmethod
    def _normalize_phone(phone):
        if not phone:
            return ''
        digits = ''.join(c for c in phone if c.isdigit())
        return digits[-9:] if len(digits) >= 9 else digits

    @staticmethod
    def _jaccard(a, b):
        sa, sb = set(a.split()), set(b.split())
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _get_or_create_duplicate_tag(self, name, color):
        category = self.env['res.partner.category']
        tag = category.search([('name', '=', name)], limit=1)
        if not tag:
            tag = category.create({'name': name, 'color': color})
        return tag

    def _run_duplicate_detection(self):
        """Detecte les doublons de contacts et applique les etiquettes correspondantes.
        Retourne un dict avec le nombre de contacts tagges par type."""
        tag_email = self._get_or_create_duplicate_tag('Doublon - Email', 1)
        tag_phone = self._get_or_create_duplicate_tag('Doublon - Telephone', 3)
        tag_name = self._get_or_create_duplicate_tag('Doublon - Nom (a verifier)', 4)

        partners = self.env['res.partner'].search([('active', '=', True)])
        rows = []
        for p in partners:
            rows.append({
                'id': p.id,
                'norm_name': self._normalize_name(p.name or ''),
                'email': self._normalize_text(p.email or ''),
                'phone': self._normalize_phone(p.phone or getattr(p, 'mobile', False) or ''),
            })

        email_groups = {}
        phone_groups = {}
        for r in rows:
            if r['email']:
                email_groups.setdefault(r['email'], []).append(r)
            if r['phone']:
                phone_groups.setdefault(r['phone'], []).append(r)

        blocks = {}
        for r in rows:
            if r['norm_name']:
                key = r['norm_name'].split(' ')[0][:4]
                blocks.setdefault(key, []).append(r)

        ids_name = set()
        threshold = 0.55
        for key, group in blocks.items():
            n = len(group)
            if n < 2:
                continue
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = group[i], group[j]
                    if self._jaccard(a['norm_name'], b['norm_name']) >= threshold:
                        ids_name.add(a['id'])
                        ids_name.add(b['id'])

        ids_email = {r['id'] for g in email_groups.values() if len(g) > 1 for r in g}
        ids_phone = {r['id'] for g in phone_groups.values() if len(g) > 1 for r in g}

        if ids_email:
            self.env['res.partner'].browse(list(ids_email)).write({'category_id': [(4, tag_email.id)]})
        if ids_phone:
            self.env['res.partner'].browse(list(ids_phone)).write({'category_id': [(4, tag_phone.id)]})
        if ids_name:
            self.env['res.partner'].browse(list(ids_name)).write({'category_id': [(4, tag_name.id)]})

        # Reinitialise le badge avant de le recalculer, pour ne pas garder
        # un statut obsolete apres une fusion de doublons
        self.env['res.partner'].search([('duplicate_status', '!=', 'none')]).write({'duplicate_status': 'none'})
        if ids_name:
            self.env['res.partner'].browse(list(ids_name)).write({'duplicate_status': 'name'})
        if ids_phone:
            self.env['res.partner'].browse(list(ids_phone)).write({'duplicate_status': 'phone'})
        if ids_email:
            self.env['res.partner'].browse(list(ids_email)).write({'duplicate_status': 'email'})

        result = {'email': len(ids_email), 'phone': len(ids_phone), 'name': len(ids_name)}
        _logger.info(
            'Detection doublons Contacts : email=%s telephone=%s nom=%s',
            result['email'], result['phone'], result['name'],
        )
        return result

    def action_detect_duplicates_button(self):
        result = self._run_duplicate_detection()
        message = (
            "Doublons email : %s\n"
            "Doublons telephone : %s\n"
            "Doublons nom (a verifier) : %s"
        ) % (result['email'], result['phone'], result['name'])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Detection des doublons terminee',
                'message': message,
                'sticky': True,
                'type': 'success',
            },
        }

    def action_detect_duplicates_cron(self):
        self._run_duplicate_detection()