{
    'name': 'Google Business Profile Manager',
    'version': '18.0.1.0.0',
    'category': 'Marketing',
    'summary': 'Manage Google Business Profiles, reviews, media and posts directly from Odoo CRM',
    'description': """
Google Business Profile Manager
================================
A production-ready Odoo 18 module that enables businesses to manage their entire
Google Business Profile presence directly within Odoo — without switching between
applications.

Key Features
------------
* **Multi-Location Management** — Connect unlimited Google Business Profile
  locations via OAuth 2.0. Each location maintains its own token lifecycle,
  synchronises addresses, phone numbers, business hours, website URLs, and
  attributes in real time.

* **Review Management** — Ingest all customer reviews from Google, display
  reviewer names, star ratings, timestamps, and review body text. Respond directly
  from Odoo using the built-in reply wizard, powered by Odoo Mail canned responses
  for fast, consistent, and brand-compliant messaging.

* **Canned Response Integration** — Leverage the ``mail.canned.response`` engine
  already present in Odoo. Pre-loaded shortcut templates cover every common
  scenario: five-star thank-you notes, service-recovery replies, food & beverage
  responses, and more. Agents type a colon-shortcut and the full reply is inserted.

* **Media Management** — Upload, categorise, and publish photos and videos to
  Google. Preserves creation date, category (EXTERIOR, INTERIOR, PRODUCT, etc.),
  and media format. Tracks publish status and engagement views per asset.

* **Posts & Announcements** — Create Google Posts (STANDARD, EVENT, OFFER) with
  calls-to-action, schedule publish/expiry dates, and monitor view and click
  engagement metrics — all from a single Kanban board.

* **Automated Synchronisation** — Scheduled cron jobs refresh location data,
  ingest new reviews, and manage token refresh automatically, keeping your
  Google profile always up to date.

* **CRM Integration** — Appears as a top-level submenu under the CRM application;
  no changes to existing CRM data or workflows.

Benefits
--------
* Unified Google Business control within the Odoo ecosystem
* Consistent, on-brand review responses using shared canned response library
* Multi-location visibility with per-location drill-down
* Reduced context-switching — your team never leaves Odoo
* Full response history auditable per review
* RTL (Arabic) ready from day one
    """,
    'author': 'Garage Systems',
    'website': 'https://www.garagesystems.io',
    'license': 'OPL-1',
    'application': False,
    'installable': True,
    'depends': [
        'base',
        'crm',
        'mail',
        'web',
    ],
    'data': [
        # 1. Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # 2. Master data
        'data/data.xml',
        # 3. Views
        'views/google_business_location_views.xml',
        'views/google_business_review_views.xml',
        'views/google_business_media_views.xml',
        'views/google_business_post_views.xml',
        'views/google_business_location_action.xml',
        'views/google_business_review_action.xml',
        'views/google_business_media_action.xml',
        'views/google_business_post_action.xml',
        'views/google_business_analytics_action.xml',
        'views/menu.xml',
        # 4. Reports
        'report/google_business_location_report.xml',
        'report/google_business_review_report.xml',
        'report/google_business_report_action.xml',
        # 5. Wizards
        'wizard/google_business_oauth_wizard_views.xml',
        'wizard/google_business_reply_wizard_views.xml',
    ],
    'demo': [
        'data/demo.xml',
    ],
}
