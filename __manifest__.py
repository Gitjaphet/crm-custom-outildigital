{
    'name': 'CRM Custom Outil Digital',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Statut contact, doublons, rattachement, assignation par equipe',
    'author': 'INTC / medevstack',
    'depends': ['contacts', 'crm'],
    'data': [
        'views/res_partner_views.xml',
        'views/crm_lead_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
