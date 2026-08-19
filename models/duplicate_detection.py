import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    duplicate_status = fields.Selection([
        ('none', 'Aucun'),
        ('name', 'Nom similaire'),
        ('phone', 'Telephone identique'),
        ('email', 'Email identique'),
    ], string='Doublon', default='none', index=True)
    duplicate_ref = fields.Char(string='Ref. doublon', index=True)
    duplicate_display = fields.Char(string='Doublon', compute='_compute_duplicate_display', store=True)

    @api.depends('duplicate_status', 'duplicate_ref')
    def _compute_duplicate_display(self):
        labels = {'email': 'Doublon Email', 'phone': 'Doublon Tel', 'name': 'Doublon Nom'}
        for p in self:
            if p.duplicate_status and p.duplicate_status != 'none' and p.duplicate_ref:
                p.duplicate_display = '%s(%s)' % (labels.get(p.duplicate_status, p.duplicate_status), p.duplicate_ref)
            else:
                p.duplicate_display = False

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

        # Union-Find pour regrouper les noms similaires en clusters
        # (pas juste des paires isolees, mais tous les contacts relies entre eux)
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        threshold = 0.55
        for key, group in blocks.items():
            n = len(group)
            if n < 2:
                continue
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = group[i], group[j]
                    if self._jaccard(a['norm_name'], b['norm_name']) >= threshold:
                        union(a['id'], b['id'])

        name_clusters = {}
        for pid in list(parent.keys()):
            root = find(pid)
            name_clusters.setdefault(root, set()).add(pid)
        name_clusters = {root: ids for root, ids in name_clusters.items() if len(ids) > 1}

        Partner = self.env['res.partner']

        # Reinitialise avant recalcul, pour ne pas garder de reference obsolete
        Partner.search(['|', ('duplicate_status', '!=', 'none'), ('duplicate_ref', '!=', False)]).write({
            'duplicate_status': 'none', 'duplicate_ref': False,
        })

        # Tags (inchange)
        ids_email = {r['id'] for g in email_groups.values() if len(g) > 1 for r in g}
        ids_phone = {r['id'] for g in phone_groups.values() if len(g) > 1 for r in g}
        ids_name = set().union(*name_clusters.values()) if name_clusters else set()

        if ids_email:
            Partner.browse(list(ids_email)).write({'category_id': [(4, tag_email.id)]})
        if ids_phone:
            Partner.browse(list(ids_phone)).write({'category_id': [(4, tag_phone.id)]})
        if ids_name:
            Partner.browse(list(ids_name)).write({'category_id': [(4, tag_name.id)]})

        # Statut + reference partagee, dans l'ordre de priorite (nom, puis
        # telephone, puis email en dernier pour ecraser en cas de chevauchement)
        idx = 0
        for root, ids in name_clusters.items():
            idx += 1
            Partner.browse(list(ids)).write({'duplicate_status': 'name', 'duplicate_ref': 'NOM-%03d' % idx})

        idx = 0
        for phone, group in phone_groups.items():
            if len(group) <= 1:
                continue
            idx += 1
            ids = [r['id'] for r in group]
            Partner.browse(ids).write({'duplicate_status': 'phone', 'duplicate_ref': 'TEL-%03d' % idx})

        idx = 0
        for email, group in email_groups.items():
            if len(group) <= 1:
                continue
            idx += 1
            ids = [r['id'] for r in group]
            Partner.browse(ids).write({'duplicate_status': 'email', 'duplicate_ref': 'EML-%03d' % idx})

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